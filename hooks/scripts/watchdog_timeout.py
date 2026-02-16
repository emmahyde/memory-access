#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
"""Watchdog that checks for timed-out tasks based on heartbeat."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def parse_iso_timestamp(value: str) -> int:
    """Parse ISO-8601 timestamp to epoch seconds."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def emit(allow: bool, code: str, reason: str, details: dict | None = None) -> int:
    """Emit validation result as JSON to stdout."""
    payload = {"allow": allow, "code": code, "reason": reason}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if allow else 1


def validate_payload_schema(payload: dict) -> tuple[bool, str, str]:
    """Validate top-level payload structure."""
    if not isinstance(payload, dict):
        return False, "SCHEMA_INVALID", "payload must be object"

    if "now" not in payload or not isinstance(payload["now"], str) or len(payload["now"]) == 0:
        return False, "MISSING_REQUIRED_INPUT", "missing required field: now"

    if "tasks" not in payload or not isinstance(payload["tasks"], list):
        return False, "MISSING_REQUIRED_INPUT", "missing required field: tasks"

    return True, "", ""


def validate_task_schema(task: dict) -> tuple[bool, str, str]:
    """Validate schema of an in_progress task."""
    task_id = task.get("task_id")
    if not task_id:
        return False, "SCHEMA_INVALID", "in_progress task missing task_id"

    timeout = task.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or timeout % 1 != 0:
        return False, "SCHEMA_INVALID", "timeout_seconds must be integer for in_progress tasks"
    if timeout < 30:
        return False, "SCHEMA_INVALID", "timeout_seconds must be >= 30 for in_progress tasks"

    heartbeat = task.get("last_heartbeat_at")
    if not heartbeat:
        return False, "SCHEMA_INVALID", "last_heartbeat_at required for in_progress tasks"

    return True, "", ""


def check_task_timeout(
    task: dict,
    now_epoch: int,
) -> tuple[bool, dict | None, str | None, str | None]:
    """
    Check if a task has timed out.

    Returns: (is_timed_out, timeout_detail, error_code, error_reason)
    """
    task_id = task["task_id"]
    timeout_seconds = int(task["timeout_seconds"])
    heartbeat_at = task["last_heartbeat_at"]

    try:
        heartbeat_epoch = parse_iso_timestamp(heartbeat_at)
    except Exception:
        return False, None, "SCHEMA_INVALID", "last_heartbeat_at must be ISO-8601 timestamp"

    age = now_epoch - heartbeat_epoch

    # Check for future heartbeat (beyond allowed clock skew)
    if age < -30:
        return False, None, "R-WD-002", "last_heartbeat_at is in the future beyond allowed clock skew"

    # Check if timed out
    if age > timeout_seconds:
        timeout_detail = {
            "task_id": task_id,
            "last_heartbeat_at": heartbeat_at,
            "timeout_seconds": timeout_seconds,
            "age_seconds": age,
        }
        return True, timeout_detail, None, None

    return False, None, None, None


def scan_tasks(tasks: list, now_epoch: int) -> tuple[bool, list[dict], str | None, str | None]:
    """
    Scan all tasks for timeouts.

    Returns: (success, timed_out_list, error_code, error_reason)
    """
    timed_out = []

    for task in tasks:
        if task.get("status") != "in_progress":
            continue

        # Validate task schema
        valid, code, reason = validate_task_schema(task)
        if not valid:
            return False, [], code, reason

        # Check for timeout
        is_timed_out, timeout_detail, code, reason = check_task_timeout(task, now_epoch)
        if code:  # Error occurred
            return False, [], code, reason
        if is_timed_out:
            timed_out.append(timeout_detail)

    return True, timed_out, None, None


def main() -> int:
    """Main validation logic."""
    payload = json.load(sys.stdin)

    # Validate payload schema
    valid, code, reason = validate_payload_schema(payload)
    if not valid:
        return emit(False, code, reason)

    # Parse timestamp
    try:
        now_epoch = parse_iso_timestamp(payload["now"])
    except Exception:
        return emit(False, "SCHEMA_INVALID", "now must be ISO-8601 timestamp")

    # Scan tasks
    success, timed_out, code, reason = scan_tasks(payload["tasks"], now_epoch)
    if not success:
        return emit(False, code or "", reason or "")

    # Decide outcome
    if len(timed_out) > 0:
        return emit(False, "R-WD-001", "task heartbeat exceeded timeout", {"timed_out": timed_out})

    return emit(True, "OK", "watchdog check passed", {"timed_out_count": 0})


if __name__ == "__main__":
    sys.exit(main())
