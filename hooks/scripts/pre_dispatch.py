#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
"""Validates pre-dispatch assignment packet with lock conflict detection."""

from __future__ import annotations

import json
import sys
from pathlib import PurePosixPath


def normalize_resource(value: str) -> str:
    """Normalize resource path to canonical form."""
    resource = value.strip().replace("\\", "/")
    if not resource:
        return ""
    normalized = str(PurePosixPath(resource))
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized


def overlaps(a: str, b: str) -> bool:
    """Check if two resource paths overlap."""
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def emit(allow: bool, code: str, reason: str, details: dict | None = None) -> int:
    """Emit validation result as JSON to stdout."""
    payload = {"allow": allow, "code": code, "reason": reason}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if allow else 1


def validate_schema(payload: dict) -> tuple[bool, str, str]:
    """Validate required fields and basic types."""
    # Top-level fields
    for field in ["task_id", "assignment", "active_locks"]:
        if field not in payload:
            return False, "R-PD-001", f"Missing required field: {field}"

    assignment = payload.get("assignment", {})
    # NOTE: heartbeat_interval_seconds was removed from requirements
    for field in ["lock_scope", "forbidden_scope", "acceptance_criteria", "worklog_path", "timeout_seconds"]:
        if field not in assignment:
            return False, "R-PD-001", f"Missing assignment field: {field}"

    # lock_scope validation
    lock_scope = assignment.get("lock_scope")
    if not isinstance(lock_scope, list) or len(lock_scope) == 0:
        return False, "R-PD-002", "lock_scope must be a non-empty array"
    if not all(isinstance(x, str) for x in lock_scope):
        return False, "R-PD-002", "lock_scope entries must be strings"

    # forbidden_scope validation
    forbidden_scope = assignment.get("forbidden_scope")
    if not isinstance(forbidden_scope, list):
        return False, "R-PD-004", "forbidden_scope must be string[]"
    if not all(isinstance(x, str) for x in forbidden_scope):
        return False, "R-PD-004", "forbidden_scope must be string[]"

    # acceptance_criteria validation
    criteria = assignment.get("acceptance_criteria")
    if not isinstance(criteria, list) or len(criteria) == 0:
        return False, "R-PD-001", "acceptance_criteria must be non-empty string[]"
    if not all(isinstance(x, str) and len(x) > 0 for x in criteria):
        return False, "R-PD-001", "acceptance_criteria must be non-empty string[]"

    # active_locks validation
    active_locks = payload.get("active_locks")
    if not isinstance(active_locks, list):
        return False, "R-PD-007", "active_locks must be an array"

    # worklog_path validation
    worklog_path = assignment.get("worklog_path")
    if not isinstance(worklog_path, str) or len(worklog_path) == 0:
        return False, "R-PD-005", "worklog_path is required"

    # timeout_seconds validation
    timeout = assignment.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or timeout < 30 or timeout % 1 != 0:
        return False, "R-PD-006", "timeout_seconds must be an integer >= 30"

    return True, "", ""


def normalize_scope(scope_raw: list[str], error_code: str, scope_name: str) -> tuple[list[str], str | None, str | None, dict | None]:
    """Normalize scope list and validate no empty resources."""
    normalized = []
    for idx, resource in enumerate(scope_raw):
        norm = normalize_resource(resource)
        if not norm:
            return [], error_code, f"{scope_name} contains empty resource after normalization", {
                "index": idx,
                "resource": resource,
            }
        normalized.append(norm)
    return normalized, None, None, None


def check_scope_overlaps(lock_scope: list[str]) -> tuple[bool, str | None, str | None, dict | None]:
    """Check that lock_scope entries don't overlap each other."""
    for i in range(len(lock_scope)):
        for j in range(i + 1, len(lock_scope)):
            if overlaps(lock_scope[i], lock_scope[j]):
                return False, "R-PD-003", "lock_scope contains overlapping resources", {
                    "a": lock_scope[i],
                    "b": lock_scope[j],
                }
    return True, None, None, None


def check_forbidden_vs_lock(lock_scope: list[str], forbidden_scope: list[str]) -> tuple[bool, str | None, str | None, dict | None]:
    """Check that forbidden_scope doesn't overlap lock_scope."""
    for own in lock_scope:
        for forbidden in forbidden_scope:
            if overlaps(own, forbidden):
                return False, "R-PD-004", "forbidden_scope overlaps lock_scope", {
                    "lock_scope": own,
                    "forbidden_scope": forbidden,
                }
    return True, None, None, None


def validate_active_lock(lock: dict, idx: int) -> tuple[bool, str, str, dict | None]:
    """Validate structure of an active lock entry."""
    if not isinstance(lock, dict):
        return False, "R-PD-007", "active_locks entries must be objects", {"index": idx}

    task_id = lock.get("task_id")
    resource = lock.get("resource")
    active = lock.get("active")

    if not isinstance(task_id, str) or not task_id:
        return False, "R-PD-007", "active_locks.task_id must be non-empty string", {"index": idx}
    if not isinstance(resource, str):
        return False, "R-PD-007", "active_locks.resource must be string", {"index": idx}
    if not isinstance(active, bool):
        return False, "R-PD-007", "active_locks.active must be bool", {"index": idx}

    return True, "", "", None


def check_lock_conflicts(
    task_id: str,
    lock_scope: list[str],
    active_locks: list,
) -> tuple[bool, str | None, str | None, dict | None]:
    """Check for conflicts with active locks from other tasks."""
    for idx, lock in enumerate(active_locks):
        valid, code, reason, details = validate_active_lock(lock, idx)
        if not valid:
            return False, code, reason, details

        lock_task_id = lock["task_id"]
        active = lock["active"]

        # Skip inactive locks or locks from the same task
        if not active or lock_task_id == task_id:
            continue

        normalized_active = normalize_resource(lock["resource"])
        if not normalized_active:
            return False, "R-PD-007", "active_locks.resource contains empty resource after normalization", {
                "index": idx,
                "resource": lock["resource"],
            }

        # Check if this active lock conflicts with our lock_scope
        for own in lock_scope:
            if overlaps(own, normalized_active):
                return False, "R-PD-003", "assignment lock_scope conflicts with active lock", {
                    "task_id": task_id,
                    "resource": own,
                    "conflict_task_id": lock_task_id,
                    "conflict_resource": normalized_active,
                }

    return True, None, None, None


def main() -> int:
    """Main validation logic."""
    payload = json.load(sys.stdin)

    # Schema validation
    valid, code, reason = validate_schema(payload)
    if not valid:
        return emit(False, code, reason)

    task_id = payload["task_id"]
    assignment = payload["assignment"]

    # Normalize scopes
    lock_scope, code, reason, details = normalize_scope(
        assignment["lock_scope"], "R-PD-002", "lock_scope"
    )
    if code is not None:
        return emit(False, code, reason or "", details)

    forbidden_scope, code, reason, details = normalize_scope(
        assignment["forbidden_scope"], "R-PD-004", "forbidden_scope"
    )
    if code is not None:
        return emit(False, code, reason or "", details)

    # Check lock_scope doesn't overlap itself
    valid, code, reason, details = check_scope_overlaps(lock_scope)
    if not valid:
        return emit(False, code or "", reason or "", details)

    # Check forbidden_scope doesn't overlap lock_scope
    valid, code, reason, details = check_forbidden_vs_lock(lock_scope, forbidden_scope)
    if not valid:
        return emit(False, code or "", reason or "", details)

    # Check for conflicts with active locks
    valid, code, reason, details = check_lock_conflicts(
        task_id, lock_scope, payload["active_locks"]
    )
    if not valid:
        return emit(False, code or "", reason or "", details)

    return emit(True, "OK", "policy checks passed")


if __name__ == "__main__":
    sys.exit(main())
