#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import PurePosixPath
from typing import Any


def emit(allow: bool, code: str, reason: str, details: dict[str, Any] | None = None) -> int:
    payload: dict[str, Any] = {"allow": allow, "code": code, "reason": reason}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if allow else 1


def normalize_resource(resource: str) -> str:
    value = resource.strip().replace("\\", "/")
    if not value:
        return ""
    normalized = str(PurePosixPath(value))
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized


def overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


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

    locks = payload.get("locks")
    if not isinstance(locks, list):
        return emit(False, "MISSING_REQUIRED_INPUT", "locks must be an array")

    normalized: list[dict[str, Any]] = []
    for idx, lock in enumerate(locks):
        if not isinstance(lock, dict):
            return emit(False, "SCHEMA_INVALID", "lock entries must be objects", {"index": idx})
        task_id = lock.get("task_id")
        resource = lock.get("resource")
        active = lock.get("active")
        if not isinstance(task_id, str) or not task_id:
            return emit(False, "SCHEMA_INVALID", "lock.task_id must be non-empty string", {"index": idx})
        if not isinstance(resource, str) or not resource.strip():
            return emit(False, "SCHEMA_INVALID", "lock.resource must be non-empty string", {"index": idx})
        if not isinstance(active, bool):
            return emit(False, "SCHEMA_INVALID", "lock.active must be bool", {"index": idx})

        normalized.append(
            {
                "task_id": task_id,
                "resource": normalize_resource(resource),
                "active": active,
            }
        )

    active_locks = [lock for lock in normalized if lock["active"]]
    conflicts: list[dict[str, str]] = []
    for i in range(len(active_locks)):
        for j in range(i + 1, len(active_locks)):
            a = active_locks[i]
            b = active_locks[j]
            if a["task_id"] == b["task_id"]:
                continue
            if overlaps(a["resource"], b["resource"]):
                conflicts.append(
                    {
                        "task_a": a["task_id"],
                        "resource_a": a["resource"],
                        "task_b": b["task_id"],
                        "resource_b": b["resource"],
                    }
                )

    if conflicts:
        return emit(False, "LOCK_CONFLICT", "overlapping active locks detected", {"conflicts": conflicts})

    return emit(True, "OK", "no active lock overlap", {"active_lock_count": len(active_locks)})


if __name__ == "__main__":
    raise SystemExit(main())
