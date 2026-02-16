#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
"""Validates lock table for conflicts."""

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


def validate_lock_entry(lock: dict, index: int) -> tuple[bool, str, str, dict | None]:
    """Validate structure of a single lock entry."""
    if not isinstance(lock, dict):
        return False, "R-LK-001", "lock entries must be objects", {"index": index}

    task_id = lock.get("task_id")
    resource = lock.get("resource")
    active = lock.get("active")

    if not isinstance(task_id, str) or not task_id:
        return False, "R-LK-001", "lock.task_id must be non-empty string", {"index": index}
    if not isinstance(resource, str):
        return False, "R-LK-001", "lock.resource must be string", {"index": index}
    if not isinstance(active, bool):
        return False, "R-LK-001", "lock.active must be bool", {"index": index}

    return True, "", "", None


def normalize_locks(locks: list) -> tuple[list[dict], str | None, str | None, dict | None]:
    """Normalize all lock entries and validate structure."""
    normalized = []
    for idx, lock in enumerate(locks):
        valid, code, reason, details = validate_lock_entry(lock, idx)
        if not valid:
            return [], code, reason, details

        normalized_resource = normalize_resource(lock["resource"])
        if not normalized_resource:
            return [], "R-LK-001", "lock.resource contains empty resource after normalization", {
                "index": idx,
                "resource": lock["resource"],
            }

        normalized.append({
            "task_id": lock["task_id"],
            "resource": normalized_resource,
            "active": lock["active"],
        })

    return normalized, None, None, None


def find_conflicts(active_locks: list[dict]) -> tuple[bool, dict | None]:
    """Check for overlapping active locks from different tasks."""
    for i in range(len(active_locks)):
        for j in range(i + 1, len(active_locks)):
            left = active_locks[i]
            right = active_locks[j]

            if left["task_id"] == right["task_id"]:
                continue

            if overlaps(left["resource"], right["resource"]):
                return False, {
                    "a": left["task_id"],
                    "b": right["task_id"],
                    "resource_a": left["resource"],
                    "resource_b": right["resource"],
                }

    return True, None


def main() -> int:
    """Main validation logic."""
    payload = json.load(sys.stdin)

    # Validate payload is an array
    if not isinstance(payload, list):
        return emit(False, "R-LK-001", "Lock table must be an array")

    # Normalize and validate all lock entries
    normalized_locks, code, reason, details = normalize_locks(payload)
    if code is not None:
        return emit(False, code, reason or "", details)

    # Filter to active locks only
    active_locks = [lock for lock in normalized_locks if lock["active"]]

    # Check for conflicts
    conflict_free, conflict_details = find_conflicts(active_locks)
    if not conflict_free:
        return emit(False, "R-LK-001", "Overlapping active locks detected", conflict_details)

    return emit(True, "OK", "lock table is conflict-free")


if __name__ == "__main__":
    sys.exit(main())
