#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from typing import Any

VALID_TASK_STATUSES = {"todo", "in_progress", "blocked", "done", "failed", "canceled"}


def emit(allow: bool, code: str, reason: str, details: dict[str, Any] | None = None) -> int:
    payload: dict[str, Any] = {"allow": allow, "code": code, "reason": reason}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if allow else 1


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return emit(False, "SCHEMA_INVALID", "empty stdin payload")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return emit(False, "SCHEMA_INVALID", "invalid JSON", {"error": str(exc)})

    if not isinstance(payload, dict):
        return emit(False, "SCHEMA_INVALID", "top-level payload must be object")

    ledger = payload.get("ledger")
    active_locks = payload.get("active_locks", [])
    events = payload.get("events", [])

    if not isinstance(ledger, list):
        return emit(False, "MISSING_REQUIRED_INPUT", "ledger must be an array")
    if not isinstance(active_locks, list):
        return emit(False, "SCHEMA_INVALID", "active_locks must be an array")
    if not isinstance(events, list):
        return emit(False, "SCHEMA_INVALID", "events must be an array")

    issues: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    for idx, task in enumerate(ledger):
        if not isinstance(task, dict):
            issues.append({"code": "SCHEMA_INVALID", "reason": "ledger entry must be object", "index": idx})
            continue

        task_id = task.get("task_id")
        status = task.get("status")
        owner = task.get("owner", "")
        dependencies = task.get("dependencies", [])

        if not isinstance(task_id, str) or not task_id:
            issues.append({"code": "SCHEMA_INVALID", "reason": "ledger.task_id missing", "index": idx})
            continue

        if task_id in by_id:
            issues.append({"code": "LEDGER_INCONSISTENT", "reason": "duplicate task_id", "task_id": task_id})
            continue

        if status not in VALID_TASK_STATUSES:
            issues.append({"code": "SCHEMA_INVALID", "reason": "invalid task status", "task_id": task_id, "status": status})

        if not isinstance(dependencies, list) or not all(isinstance(dep, str) for dep in dependencies):
            issues.append({"code": "SCHEMA_INVALID", "reason": "dependencies must be string[]", "task_id": task_id})
            dependencies = []

        if status == "in_progress" and (not isinstance(owner, str) or not owner.strip()):
            issues.append({"code": "LEDGER_INCONSISTENT", "reason": "in_progress task missing owner", "task_id": task_id})

        by_id[task_id] = {
            "task": task,
            "status": status,
            "dependencies": dependencies,
        }

    for task_id, entry in by_id.items():
        for dep_id in entry["dependencies"]:
            if dep_id not in by_id:
                issues.append(
                    {
                        "code": "LEDGER_INCONSISTENT",
                        "reason": "dependency missing from ledger",
                        "task_id": task_id,
                        "depends_on": dep_id,
                    }
                )
                continue

            dep_status = by_id[dep_id]["status"]
            if entry["status"] in {"in_progress", "done"} and dep_status != "done":
                issues.append(
                    {
                        "code": "DEPENDENCY_NOT_MET",
                        "reason": "task advanced before dependency done",
                        "task_id": task_id,
                        "depends_on": dep_id,
                        "depends_on_status": dep_status,
                    }
                )

    for idx, lock in enumerate(active_locks):
        if not isinstance(lock, dict):
            issues.append({"code": "SCHEMA_INVALID", "reason": "active_locks entry must be object", "index": idx})
            continue

        task_id = lock.get("task_id")
        active = lock.get("active", False)

        if not isinstance(task_id, str) or not task_id:
            issues.append({"code": "SCHEMA_INVALID", "reason": "active_locks.task_id invalid", "index": idx})
            continue
        if task_id not in by_id:
            issues.append({"code": "LEDGER_INCONSISTENT", "reason": "active lock references unknown task", "task_id": task_id})
            continue

        if active and by_id[task_id]["status"] in {"done", "failed", "canceled"}:
            issues.append(
                {
                    "code": "LEDGER_INCONSISTENT",
                    "reason": "terminal task still has active lock",
                    "task_id": task_id,
                }
            )

    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            issues.append({"code": "SCHEMA_INVALID", "reason": "event entry must be object", "index": idx})
            continue
        task_id = event.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            issues.append({"code": "SCHEMA_INVALID", "reason": "event.task_id invalid", "index": idx})
            continue
        if task_id not in by_id:
            issues.append({"code": "LEDGER_INCONSISTENT", "reason": "event references unknown task", "task_id": task_id})

    if issues:
        return emit(False, "LEDGER_INCONSISTENT", "ledger reconciliation found inconsistencies", {"issues": issues})

    summary = {
        "task_count": len(by_id),
        "active_lock_count": len([lock for lock in active_locks if isinstance(lock, dict) and lock.get("active") is True]),
        "event_count": len(events),
    }
    return emit(True, "OK", "ledger reconciliation passed", summary)


if __name__ == "__main__":
    raise SystemExit(main())
