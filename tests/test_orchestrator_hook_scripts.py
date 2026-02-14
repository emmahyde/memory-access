from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


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


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text())


def _pre_dispatch_payload(
    *,
    task_id: str = "T-12",
    lock_scope: list[str] | None = None,
    forbidden_scope: list[str] | None = None,
    active_locks: list[dict] | None = None,
) -> dict:
    return {
        "task_id": task_id,
        "assignment": {
            "lock_scope": lock_scope or ["src/a.py"],
            "forbidden_scope": forbidden_scope or ["src/secret"],
            "acceptance_criteria": ["tests pass"],
            "worklog_path": "worklogs/T-12.jsonl",
            "timeout_seconds": 1200,
            "heartbeat_interval_seconds": 120,
        },
        "active_locks": active_locks or [],
    }


def _post_execution_payload(worklog_path: str, *, result: dict | None = None, assignment: dict | None = None) -> dict:
    return {
        "task_id": "T-12",
        "result": result
        or {
            "status": "done",
            "changes": [{"resource": "src/a.py", "action": "edit"}],
            "acceptance_check": [{"criterion": "tests pass", "status": "pass", "evidence": "pytest"}],
            "worklog_path": worklog_path,
            "notes_for_orchestrator": ["ready"],
        },
        "assignment": assignment or {"lock_scope": ["src"], "forbidden_scope": ["src/secret"]},
    }


def test_pre_dispatch_allows_valid_payload() -> None:
    code, output = _run_hook(
        "pre-dispatch.sh",
        _pre_dispatch_payload(
            active_locks=[{"task_id": "T-9", "resource": "docs/notes.md", "active": True}],
        ),
    )
    assert code == 0
    assert output["allow"] is True
    assert output["code"] == "OK"


def test_pre_dispatch_blocks_prefix_lock_conflict() -> None:
    code, output = _run_hook(
        "pre-dispatch.sh",
        _pre_dispatch_payload(
            lock_scope=["src/api/handler.py"],
            forbidden_scope=[],
            active_locks=[{"task_id": "T-9", "resource": "src", "active": True}],
        ),
    )
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "R-PD-003"


def test_pre_dispatch_blocks_malformed_active_lock_record() -> None:
    code, output = _run_hook(
        "pre-dispatch.sh",
        _pre_dispatch_payload(active_locks=[{"task_id": "T-9", "resource": "src/a.py", "active": "true"}]),
    )
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "R-PD-007"


def test_post_execution_allows_valid_changes_within_scope(tmp_path) -> None:
    worklog_path = tmp_path / "T-12.jsonl"
    worklog_path.write_text("")
    code, output = _run_hook("post-execution.sh", _post_execution_payload(str(worklog_path)))
    assert code == 0
    assert output["allow"] is True
    assert output["code"] == "OK"


def test_post_execution_blocks_out_of_scope_change(tmp_path) -> None:
    worklog_path = tmp_path / "T-12.jsonl"
    worklog_path.write_text("")
    payload = _post_execution_payload(
        str(worklog_path),
        result={
            "status": "done",
            "changes": [{"resource": "tests/test_api.py", "action": "edit"}],
            "acceptance_check": [{"criterion": "tests pass", "status": "pass", "evidence": "pytest"}],
            "worklog_path": str(worklog_path),
            "notes_for_orchestrator": ["ready"],
        },
        assignment={"lock_scope": ["src"], "forbidden_scope": []},
    )
    code, output = _run_hook("post-execution.sh", payload)
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "R-PO-002"


def test_post_execution_blocks_forbidden_scope_overlap(tmp_path) -> None:
    worklog_path = tmp_path / "T-12.jsonl"
    worklog_path.write_text("")
    payload = _post_execution_payload(
        str(worklog_path),
        result={
            "status": "done",
            "changes": [{"resource": "src/secret/keys.py", "action": "edit"}],
            "acceptance_check": [{"criterion": "tests pass", "status": "pass", "evidence": "pytest"}],
            "worklog_path": str(worklog_path),
            "notes_for_orchestrator": ["ready"],
        },
        assignment={"lock_scope": ["src"], "forbidden_scope": ["src/secret"]},
    )
    code, output = _run_hook("post-execution.sh", payload)
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "R-PW-002"


def test_post_execution_blocks_secret_note(tmp_path) -> None:
    worklog_path = tmp_path / "T-12.jsonl"
    worklog_path.write_text("")
    payload = _post_execution_payload(
        str(worklog_path),
        result={
            "status": "blocked",
            "changes": [],
            "acceptance_check": [],
            "worklog_path": str(worklog_path),
            "notes_for_orchestrator": ["OPENAI_API_KEY=sk-abc1234567890123456789012345"],
        },
    )
    code, output = _run_hook("post-execution.sh", payload)
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "R-PO-004"


def test_on_lock_update_allows_non_overlapping_active_locks() -> None:
    payload = [
        {"task_id": "T-1", "resource": "src/a.py", "active": True},
        {"task_id": "T-2", "resource": "src/b.py", "active": True},
        {"task_id": "T-3", "resource": "src", "active": False},
    ]
    code, output = _run_hook("on-lock-update.sh", payload)
    assert code == 0
    assert output["allow"] is True
    assert output["code"] == "OK"


def test_on_lock_update_blocks_prefix_overlap() -> None:
    payload = [
        {"task_id": "T-1", "resource": "src", "active": True},
        {"task_id": "T-2", "resource": "src/a.py", "active": True},
    ]
    code, output = _run_hook("on-lock-update.sh", payload)
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "R-LK-001"


def test_on_lock_update_blocks_empty_normalized_resource() -> None:
    payload = [{"task_id": "T-1", "resource": "   ", "active": True}]
    code, output = _run_hook("on-lock-update.sh", payload)
    assert code != 0
    assert output["allow"] is False
    assert output["code"] == "R-LK-001"


def test_assignment_validator_and_predispatch_hook_parity_valid() -> None:
    packet = _load_example("01-assignment-valid.json")
    v_code, v_out = _run_validator("validate_packet.py", packet)
    assert v_code == 0
    assert v_out["allow"] is True

    hook_payload = {
        "task_id": packet["task"]["task_id"],
        "assignment": {
            "lock_scope": packet["task"]["lock_scope"],
            "forbidden_scope": packet["task"]["forbidden_scope"],
            "acceptance_criteria": packet["task"]["acceptance_criteria"],
            "worklog_path": packet["task"]["worklog_path"],
            "timeout_seconds": packet["task"]["timeout_seconds"],
            "heartbeat_interval_seconds": packet["task"]["heartbeat_interval_seconds"],
        },
        "active_locks": packet["active_locks"],
    }
    h_code, h_out = _run_hook("pre-dispatch.sh", hook_payload)
    assert h_code == 0
    assert h_out["allow"] is True


def test_assignment_validator_and_predispatch_hook_parity_conflict() -> None:
    packet = _load_example("01-assignment-valid.json")
    packet["task"]["lock_scope"] = ["src/api/handler.py"]
    packet["task"]["forbidden_scope"] = []
    packet["active_locks"] = [{"task_id": "T-9", "resource": "src", "active": True}]

    v_code, v_out = _run_validator("validate_packet.py", packet)
    assert v_code != 0
    assert v_out["allow"] is False
    assert v_out["code"] == "LOCK_CONFLICT"

    hook_payload = {
        "task_id": packet["task"]["task_id"],
        "assignment": {
            "lock_scope": packet["task"]["lock_scope"],
            "forbidden_scope": packet["task"]["forbidden_scope"],
            "acceptance_criteria": packet["task"]["acceptance_criteria"],
            "worklog_path": packet["task"]["worklog_path"],
            "timeout_seconds": packet["task"]["timeout_seconds"],
            "heartbeat_interval_seconds": packet["task"]["heartbeat_interval_seconds"],
        },
        "active_locks": packet["active_locks"],
    }
    h_code, h_out = _run_hook("pre-dispatch.sh", hook_payload)
    assert h_code != 0
    assert h_out["allow"] is False
    assert h_out["code"] == "R-PD-003"


def test_result_validator_and_post_execution_hook_parity_empty_done_acceptance(tmp_path) -> None:
    result_payload = _load_example("03-result-invalid-empty-acceptance.json")
    v_code, v_out = _run_validator("validate_result.py", result_payload)
    assert v_code != 0
    assert v_out["allow"] is False
    assert v_out["code"] == "ACCEPTANCE_FAILED"

    worklog_path = tmp_path / "T-12.jsonl"
    worklog_path.write_text("")
    hook_payload = _post_execution_payload(
        str(worklog_path),
        result={
            **result_payload,
            "worklog_path": str(worklog_path),
        },
        assignment={"lock_scope": ["tests"], "forbidden_scope": []},
    )
    h_code, h_out = _run_hook("post-execution.sh", hook_payload)
    assert h_code != 0
    assert h_out["allow"] is False
    assert h_out["code"] == "R-PC-001"


def test_result_validator_and_post_execution_hook_parity_secret_note(tmp_path) -> None:
    result_payload = _load_example("03-result-invalid-secret-note.json")
    v_code, v_out = _run_validator("validate_result.py", result_payload)
    assert v_code != 0
    assert v_out["allow"] is False
    assert v_out["code"] == "UNTRUSTED_CONTEXT_BLOCK"

    worklog_path = tmp_path / "T-12.jsonl"
    worklog_path.write_text("")
    hook_payload = _post_execution_payload(
        str(worklog_path),
        result={
            **result_payload,
            "worklog_path": str(worklog_path),
        },
        assignment={"lock_scope": ["tests"], "forbidden_scope": []},
    )
    h_code, h_out = _run_hook("post-execution.sh", hook_payload)
    assert h_code != 0
    assert h_out["allow"] is False
    assert h_out["code"] == "R-PO-004"
