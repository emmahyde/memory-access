#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import PurePosixPath
from typing import Any

TASK_ID_RE = re.compile(r"^(T-[0-9]+|[0-9a-fA-F-]{36})$")
RUN_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


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


def validate_schema_version(value: Any) -> tuple[bool, str]:
    if not isinstance(value, str) or not value:
        return False, "schema_version must be a non-empty string"
    major = value.split(".", 1)[0]
    if major != "1":
        return False, f"unsupported schema major version: {value}"
    return True, ""


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return emit(False, "SCHEMA_INVALID", "empty stdin payload")

    try:
        packet = json.loads(raw)
    except json.JSONDecodeError as exc:
        return emit(False, "SCHEMA_INVALID", "invalid JSON", {"error": str(exc)})

    if not isinstance(packet, dict):
        return emit(False, "SCHEMA_INVALID", "top-level payload must be an object")

    required = [
        "schema_version",
        "run_id",
        "packet_type",
        "global_objective",
        "task",
        "active_locks",
        "context_package",
        "required_output_schema",
    ]
    missing = [key for key in required if key not in packet]
    if missing:
        return emit(False, "MISSING_REQUIRED_INPUT", "missing required fields", {"missing": missing})

    ok, msg = validate_schema_version(packet["schema_version"])
    if not ok:
        return emit(False, "UNKNOWN_SCHEMA_VERSION", msg)

    if not isinstance(packet["run_id"], str) or not RUN_ID_RE.match(packet["run_id"]):
        return emit(False, "SCHEMA_INVALID", "run_id must be UUID-like")

    if packet["packet_type"] != "assignment":
        return emit(False, "SCHEMA_INVALID", "packet_type must be 'assignment'")

    if not isinstance(packet["global_objective"], str) or not packet["global_objective"].strip():
        return emit(False, "MISSING_REQUIRED_INPUT", "global_objective must be non-empty")

    if packet["required_output_schema"] != "subagent_result_v1":
        return emit(False, "SCHEMA_INVALID", "required_output_schema must be 'subagent_result_v1'")

    task = packet["task"]
    if not isinstance(task, dict):
        return emit(False, "SCHEMA_INVALID", "task must be an object")

    task_required = [
        "task_id",
        "title",
        "type",
        "dependencies",
        "lock_scope",
        "forbidden_scope",
        "acceptance_criteria",
        "worklog_path",
        "timeout_seconds",
    ]
    missing_task = [key for key in task_required if key not in task]
    if missing_task:
        return emit(False, "MISSING_REQUIRED_INPUT", "missing required task fields", {"missing": missing_task})

    task_id = task["task_id"]
    if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
        return emit(False, "SCHEMA_INVALID", "task.task_id must match expected format")

    if task["type"] not in {"parallelizable", "serial"}:
        return emit(False, "SCHEMA_INVALID", "task.type must be parallelizable|serial")

    priority = task.get("priority", "normal")
    if priority not in {"low", "normal", "high", "critical"}:
        return emit(False, "SCHEMA_INVALID", "task.priority must be low|normal|high|critical")

    if not isinstance(task["dependencies"], list):
        return emit(False, "SCHEMA_INVALID", "task.dependencies must be string[]")
    for idx, dep in enumerate(task["dependencies"]):
        if not isinstance(dep, str) or not TASK_ID_RE.match(dep):
            return emit(
                False,
                "SCHEMA_INVALID",
                "task.dependencies entries must match task_id format",
                {"index": idx, "dependency": dep},
            )

    lock_scope_raw = task["lock_scope"]
    if not isinstance(lock_scope_raw, list) or not lock_scope_raw:
        return emit(False, "MISSING_REQUIRED_INPUT", "task.lock_scope must be a non-empty array")
    if not all(isinstance(item, str) for item in lock_scope_raw):
        return emit(False, "SCHEMA_INVALID", "task.lock_scope must be string[]")

    forbidden_scope_raw = task["forbidden_scope"]
    if not isinstance(forbidden_scope_raw, list) or not all(isinstance(item, str) for item in forbidden_scope_raw):
        return emit(False, "SCHEMA_INVALID", "task.forbidden_scope must be string[]")

    acceptance = task["acceptance_criteria"]
    if not isinstance(acceptance, list) or not acceptance or not all(isinstance(item, str) and item.strip() for item in acceptance):
        return emit(False, "MISSING_REQUIRED_INPUT", "task.acceptance_criteria must be non-empty string[]")

    if not isinstance(task["worklog_path"], str) or not task["worklog_path"].strip():
        return emit(False, "MISSING_REQUIRED_INPUT", "task.worklog_path must be non-empty")

    timeout_seconds = task["timeout_seconds"]
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 30:
        return emit(False, "SCHEMA_INVALID", "task.timeout_seconds must be int >= 30")

    if not isinstance(packet["context_package"], list):
        return emit(False, "SCHEMA_INVALID", "context_package must be an array")

    for idx, item in enumerate(packet["context_package"]):
        if not isinstance(item, dict):
            return emit(False, "SCHEMA_INVALID", "context_package entries must be objects", {"index": idx})
        kind = item.get("kind")
        value = item.get("value")
        if kind not in {"file", "note", "command", "constraint"}:
            return emit(False, "SCHEMA_INVALID", "context_package.kind invalid", {"index": idx, "kind": kind})
        if not isinstance(value, str) or not value.strip():
            return emit(False, "SCHEMA_INVALID", "context_package.value must be non-empty string", {"index": idx})

    active_locks = packet["active_locks"]
    if not isinstance(active_locks, list):
        return emit(False, "SCHEMA_INVALID", "active_locks must be an array")

    normalized_scope: list[str] = []
    for idx, resource in enumerate(lock_scope_raw):
        normalized = normalize_resource(resource)
        if not normalized:
            return emit(
                False,
                "SCHEMA_INVALID",
                "task.lock_scope contains empty resource after normalization",
                {"index": idx, "resource": resource},
            )
        normalized_scope.append(normalized)

    normalized_forbidden: list[str] = []
    for idx, resource in enumerate(forbidden_scope_raw):
        normalized = normalize_resource(resource)
        if not normalized:
            return emit(
                False,
                "SCHEMA_INVALID",
                "task.forbidden_scope contains empty resource after normalization",
                {"index": idx, "resource": resource},
            )
        normalized_forbidden.append(normalized)

    for a in normalized_scope:
        for b in normalized_forbidden:
            if b and overlaps(a, b):
                return emit(
                    False,
                    "SCOPE_VIOLATION",
                    "forbidden_scope overlaps lock_scope",
                    {"lock_scope": a, "forbidden_scope": b},
                )

    for i in range(len(normalized_scope)):
        for j in range(i + 1, len(normalized_scope)):
            if overlaps(normalized_scope[i], normalized_scope[j]):
                return emit(
                    False,
                    "LOCK_CONFLICT",
                    "lock_scope contains overlapping resources",
                    {"a": normalized_scope[i], "b": normalized_scope[j]},
                )

    for idx, lock in enumerate(active_locks):
        if not isinstance(lock, dict):
            return emit(False, "SCHEMA_INVALID", "active_locks entries must be objects", {"index": idx})

        lock_task_id = lock.get("task_id")
        resource = lock.get("resource")
        active = lock.get("active")

        if not isinstance(lock_task_id, str) or not TASK_ID_RE.match(lock_task_id):
            return emit(False, "SCHEMA_INVALID", "active_locks.task_id must match task_id format", {"index": idx})
        if not isinstance(resource, str):
            return emit(False, "SCHEMA_INVALID", "active_locks.resource must be string", {"index": idx})
        if not isinstance(active, bool):
            return emit(False, "SCHEMA_INVALID", "active_locks.active must be bool", {"index": idx})

        if not active or lock_task_id == task_id:
            continue

        normalized_active = normalize_resource(resource)
        if not normalized_active:
            return emit(
                False,
                "SCHEMA_INVALID",
                "active_locks.resource normalizes to empty",
                {"index": idx, "resource": resource},
            )
        for own in normalized_scope:
            if overlaps(own, normalized_active):
                return emit(
                    False,
                    "LOCK_CONFLICT",
                    "assignment lock_scope conflicts with active locks",
                    {
                        "task_id": task_id,
                        "resource": own,
                        "conflict_task_id": lock_task_id,
                        "conflict_resource": normalized_active,
                    },
                )

    return emit(True, "OK", "assignment packet valid")


if __name__ == "__main__":
    raise SystemExit(main())
