from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import aiosqlite
import pytest

pytest.importorskip("peewee")

from memory_access.models import TaskState
from memory_access.storage import InsightStore
from memory_access.task_store import TaskStore


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SCRIPTS_DIR = REPO_ROOT / "hooks" / "scripts"
VALIDATOR_SCRIPTS_DIR = REPO_ROOT / "skills" / "multi-agent-operator-guide" / "scripts"
EXAMPLES_DIR = REPO_ROOT / "skills" / "multi-agent-operator-guide" / "examples"


def _run_hook(script_name: str, payload: dict | list) -> tuple[int, dict]:
    proc = subprocess.run(
        ["bash", str(HOOK_SCRIPTS_DIR / script_name)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.stdout.strip(), f"expected JSON stdout from {script_name}, stderr={proc.stderr!r}"
    return proc.returncode, json.loads(proc.stdout)


def _run_validator(script_name: str, payload: dict) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPTS_DIR / script_name)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.stdout.strip(), f"expected JSON stdout from {script_name}, stderr={proc.stderr!r}"
    return proc.returncode, json.loads(proc.stdout)


def _run_reconcile(payload: dict) -> tuple[int, dict]:
    return _run_validator("reconcile_ledger.py", payload)


def _load_expected_trace(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text())


async def _load_active_locks(db_path: str) -> list[dict]:
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            SELECT task_id, resource, active
            FROM task_locks
            WHERE active = 1
            ORDER BY task_id, resource
            """
        )
        rows = await cursor.fetchall()
    return [{"task_id": row[0], "resource": row[1], "active": bool(row[2])} for row in rows]


def _assignment_packet(
    *,
    run_id: str,
    task_id: str,
    lock_scope: list[str],
    forbidden_scope: list[str],
    worklog_path: str,
    active_locks: list[dict],
) -> dict:
    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "packet_type": "assignment",
        "global_objective": "Demonstrate deterministic orchestration flow",
        "task": {
            "task_id": task_id,
            "title": "E2E task",
            "type": "parallelizable",
            "dependencies": [],
            "lock_scope": lock_scope,
            "forbidden_scope": forbidden_scope,
            "acceptance_criteria": ["pytest -q passes"],
            "worklog_path": worklog_path,
            "timeout_seconds": 1200,
            "heartbeat_interval_seconds": 120,
            "priority": "high",
        },
        "active_locks": active_locks,
        "context_package": [
            {"kind": "file", "value": "tests/test_orchestrator_e2e.py"},
            {"kind": "constraint", "value": "Do not modify forbidden scope"},
        ],
        "required_output_schema": "subagent_result_v1",
    }


def _assignment_to_pre_dispatch(assignment_packet: dict) -> dict:
    task = assignment_packet["task"]
    return {
        "task_id": task["task_id"],
        "assignment": {
            "lock_scope": task["lock_scope"],
            "forbidden_scope": task["forbidden_scope"],
            "acceptance_criteria": task["acceptance_criteria"],
            "worklog_path": task["worklog_path"],
            "timeout_seconds": task["timeout_seconds"],
            "heartbeat_interval_seconds": task["heartbeat_interval_seconds"],
        },
        "active_locks": assignment_packet["active_locks"],
    }


def _result_packet(*, run_id: str, task_id: str, worklog_path: str, changed_resource: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "task_id": task_id,
        "status": "done",
        "changes": [{"resource": changed_resource, "action": "edit", "evidence": "Added e2e assertions"}],
        "acceptance_check": [{"criterion": "pytest -q passes", "status": "pass", "evidence": "pytest -q"}],
        "worklog_path": worklog_path,
        "notes_for_orchestrator": ["No conflicts detected."],
    }


async def _ledger_payload(task_store: TaskStore, task_ids: list[str], db_path: str) -> dict:
    tasks = [await task_store.get_task(task_id) for task_id in task_ids]
    ledger = [
        {
            "task_id": task.task_id,
            "status": task.status.value,
            "owner": task.owner,
            "dependencies": [],
        }
        for task in tasks
        if task is not None
    ]
    ledger.sort(key=lambda item: item["task_id"])

    events: list[dict] = []
    for task_id in sorted(task_ids):
        for event in await task_store.list_events(task_id, limit=50):
            events.append({"task_id": event.task_id, "event_type": event.event_type})

    return {
        "ledger": ledger,
        "active_locks": await _load_active_locks(db_path),
        "events": events,
    }


@pytest.mark.asyncio
async def test_e2e_success_flow_matches_illustrative_output(tmp_db, tmp_path) -> None:
    store = InsightStore(tmp_db)
    await store.initialize()
    task_store = TaskStore(tmp_db)

    holder = await task_store.create_task("holder", task_id="T-199")
    main = await task_store.create_task("e2e success", owner="agent-e2e", task_id="T-200")
    await task_store.assign_locks(holder.task_id, ["src/api.py"])

    assignment = _assignment_packet(
        run_id="11111111-1111-1111-1111-111111111111",
        task_id=main.task_id,
        lock_scope=["tests/test_orchestrator_e2e.py"],
        forbidden_scope=["src"],
        worklog_path="worklogs/T-200.jsonl",
        active_locks=await _load_active_locks(tmp_db),
    )

    validate_packet_code, validate_packet_out = _run_validator("validate_packet.py", assignment)
    pre_dispatch_code, pre_dispatch_out = _run_hook("pre-dispatch.sh", _assignment_to_pre_dispatch(assignment))

    await task_store.assign_locks(main.task_id, assignment["task"]["lock_scope"])
    in_progress = await task_store.transition(
        main.task_id,
        from_state=TaskState.TODO,
        to_state=TaskState.IN_PROGRESS,
        actor="orchestrator",
        expected_version=main.version,
        reason="dispatch",
        evidence="pre-dispatch ok",
    )

    worklog_path = tmp_path / "T-200.jsonl"
    worklog_path.write_text('{"seq":1,"event":"start"}\n')
    result = _result_packet(
        run_id=assignment["run_id"],
        task_id=main.task_id,
        worklog_path=str(worklog_path),
        changed_resource="tests/test_orchestrator_e2e.py",
    )

    validate_result_code, validate_result_out = _run_validator("validate_result.py", result)
    post_execution_code, post_execution_out = _run_hook(
        "post-execution.sh",
        {
            "task_id": main.task_id,
            "result": result,
            "assignment": {
                "lock_scope": assignment["task"]["lock_scope"],
                "forbidden_scope": assignment["task"]["forbidden_scope"],
            },
        },
    )

    done = await task_store.transition(
        main.task_id,
        from_state=TaskState.IN_PROGRESS,
        to_state=TaskState.DONE,
        actor="orchestrator",
        expected_version=in_progress.task.version,
        reason="accepted result",
        evidence="validator + post-execution ok",
    )
    await task_store.release_locks(main.task_id)

    active_locks = await _load_active_locks(tmp_db)
    lock_update_code, lock_update_out = _run_hook("on-lock-update.sh", active_locks)

    reconcile_code, reconcile_out = _run_reconcile(await _ledger_payload(task_store, [holder.task_id, main.task_id], tmp_db))

    watchdog_code, watchdog_out = _run_hook(
        "watchdog-timeout.sh",
        {
            "now": "2026-02-14T20:00:00Z",
            "tasks": [
                {"task_id": holder.task_id, "status": "todo"},
                {"task_id": main.task_id, "status": "done"},
            ],
        },
    )

    trace = {
        "scenario": "success",
        "task_id": main.task_id,
        "steps": [
            {
                "step": "validate_packet",
                "exit_code": validate_packet_code,
                "allow": validate_packet_out["allow"],
                "code": validate_packet_out["code"],
                "reason": validate_packet_out["reason"],
            },
            {
                "step": "pre_dispatch",
                "exit_code": pre_dispatch_code,
                "allow": pre_dispatch_out["allow"],
                "code": pre_dispatch_out["code"],
                "reason": pre_dispatch_out["reason"],
            },
            {
                "step": "transition_in_progress",
                "status": in_progress.task.status.value,
                "version": in_progress.task.version,
            },
            {
                "step": "validate_result",
                "exit_code": validate_result_code,
                "allow": validate_result_out["allow"],
                "code": validate_result_out["code"],
                "reason": validate_result_out["reason"],
            },
            {
                "step": "post_execution",
                "exit_code": post_execution_code,
                "allow": post_execution_out["allow"],
                "code": post_execution_out["code"],
                "reason": post_execution_out["reason"],
            },
            {
                "step": "transition_done",
                "status": done.task.status.value,
                "version": done.task.version,
            },
            {
                "step": "active_locks_after_release",
                "active_locks": active_locks,
            },
            {
                "step": "on_lock_update",
                "exit_code": lock_update_code,
                "allow": lock_update_out["allow"],
                "code": lock_update_out["code"],
                "reason": lock_update_out["reason"],
            },
            {
                "step": "reconcile_ledger",
                "exit_code": reconcile_code,
                "allow": reconcile_out["allow"],
                "code": reconcile_out["code"],
                "reason": reconcile_out["reason"],
                "details": reconcile_out["details"],
            },
            {
                "step": "watchdog",
                "exit_code": watchdog_code,
                "allow": watchdog_out["allow"],
                "code": watchdog_out["code"],
                "reason": watchdog_out["reason"],
                "details": watchdog_out["details"],
            },
        ],
    }

    assert trace == _load_expected_trace("05-e2e-success-trace.output.json")


@pytest.mark.asyncio
async def test_e2e_timeout_recovery_flow_matches_illustrative_output(tmp_db) -> None:
    store = InsightStore(tmp_db)
    await store.initialize()
    task_store = TaskStore(tmp_db)

    task = await task_store.create_task("e2e timeout", owner="agent-e2e", task_id="T-300")
    await task_store.assign_locks(task.task_id, ["src/feature.py"])

    in_progress = await task_store.transition(
        task.task_id,
        from_state=TaskState.TODO,
        to_state=TaskState.IN_PROGRESS,
        actor="orchestrator",
        expected_version=task.version,
        reason="dispatch",
        evidence="initial assignment",
    )

    watchdog_code, watchdog_out = _run_hook(
        "watchdog-timeout.sh",
        {
            "now": "2026-02-14T20:00:00Z",
            "tasks": [
                {
                    "task_id": task.task_id,
                    "status": "in_progress",
                    "last_heartbeat_at": "2026-02-14T19:20:00Z",
                    "timeout_seconds": 1200,
                }
            ],
        },
    )

    blocked = await task_store.transition(
        task.task_id,
        from_state=TaskState.IN_PROGRESS,
        to_state=TaskState.BLOCKED,
        actor="orchestrator",
        expected_version=in_progress.task.version,
        reason="TASK_TIMEOUT",
        evidence="watchdog R-WD-001",
    )
    released = await task_store.release_locks(task.task_id)
    replanned = await task_store.transition(
        task.task_id,
        from_state=TaskState.BLOCKED,
        to_state=TaskState.TODO,
        actor="orchestrator",
        expected_version=blocked.task.version,
        reason="refresh context complete",
        evidence="blocked->todo replanning",
    )

    active_locks = await _load_active_locks(tmp_db)
    lock_update_code, lock_update_out = _run_hook("on-lock-update.sh", active_locks)

    assignment = _assignment_packet(
        run_id="22222222-2222-2222-2222-222222222222",
        task_id=task.task_id,
        lock_scope=["src/feature.py"],
        forbidden_scope=["src/secret"],
        worklog_path="worklogs/T-300.jsonl",
        active_locks=active_locks,
    )
    validate_packet_code, validate_packet_out = _run_validator("validate_packet.py", assignment)
    pre_dispatch_code, pre_dispatch_out = _run_hook("pre-dispatch.sh", _assignment_to_pre_dispatch(assignment))

    timeout_details = watchdog_out.get("details", {}).get("timed_out", [{}])[0]
    trace = {
        "scenario": "timeout_recovery",
        "task_id": task.task_id,
        "steps": [
            {
                "step": "transition_in_progress",
                "status": in_progress.task.status.value,
                "version": in_progress.task.version,
            },
            {
                "step": "watchdog_timeout",
                "exit_code": watchdog_code,
                "allow": watchdog_out["allow"],
                "code": watchdog_out["code"],
                "reason": watchdog_out["reason"],
                "timed_out_task_id": timeout_details.get("task_id"),
                "age_seconds": timeout_details.get("age_seconds"),
            },
            {
                "step": "transition_blocked",
                "status": blocked.task.status.value,
                "version": blocked.task.version,
                "retry_count": blocked.task.retry_count,
            },
            {
                "step": "release_locks",
                "released": released,
            },
            {
                "step": "transition_todo",
                "status": replanned.task.status.value,
                "version": replanned.task.version,
                "retry_count": replanned.task.retry_count,
            },
            {
                "step": "active_locks_after_release",
                "active_locks": active_locks,
            },
            {
                "step": "on_lock_update",
                "exit_code": lock_update_code,
                "allow": lock_update_out["allow"],
                "code": lock_update_out["code"],
                "reason": lock_update_out["reason"],
            },
            {
                "step": "validate_packet",
                "exit_code": validate_packet_code,
                "allow": validate_packet_out["allow"],
                "code": validate_packet_out["code"],
                "reason": validate_packet_out["reason"],
            },
            {
                "step": "pre_dispatch",
                "exit_code": pre_dispatch_code,
                "allow": pre_dispatch_out["allow"],
                "code": pre_dispatch_out["code"],
                "reason": pre_dispatch_out["reason"],
            },
        ],
    }

    assert trace == _load_expected_trace("06-e2e-timeout-recovery-trace.output.json")
