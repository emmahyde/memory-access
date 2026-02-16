#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
"""Validates post-execution result and scope enforcement."""

from __future__ import annotations

import json
import os
import re
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


def within(candidate: str, scope: str) -> bool:
    """Check if candidate path is within scope path."""
    return candidate == scope or candidate.startswith(scope + "/")


def emit(allow: bool, code: str, reason: str, details: dict | None = None) -> int:
    """Emit validation result as JSON to stdout."""
    payload = {"allow": allow, "code": code, "reason": reason}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if allow else 1


def validate_schema(payload: dict) -> tuple[bool, str, str]:
    """Validate required fields and types."""
    # Top-level fields
    for field in ["task_id", "result", "assignment"]:
        if field not in payload:
            return False, "R-PO-001", f"Missing required field: {field}"

    result = payload.get("result", {})
    for field in ["status", "changes", "acceptance_check", "worklog_path", "notes_for_orchestrator"]:
        if field not in result:
            return False, "R-PO-001", f"Missing result field: {field}"

    # Type checks
    if not isinstance(result.get("changes"), list):
        return False, "R-PO-001", "result.changes must be an array"

    assignment = payload.get("assignment", {})
    lock_scope = assignment.get("lock_scope")
    forbidden_scope = assignment.get("forbidden_scope")
    notes = result.get("notes_for_orchestrator")

    if not isinstance(lock_scope, list) or len(lock_scope) == 0:
        return False, "R-PO-001", "assignment.lock_scope must be non-empty string[]"
    if not all(isinstance(x, str) for x in lock_scope):
        return False, "R-PO-001", "assignment.lock_scope must be non-empty string[]"

    if not isinstance(forbidden_scope, list):
        return False, "R-PO-001", "assignment.forbidden_scope must be string[]"
    if not all(isinstance(x, str) for x in forbidden_scope):
        return False, "R-PO-001", "assignment.forbidden_scope must be string[]"

    if not isinstance(notes, list):
        return False, "R-PO-001", "result.notes_for_orchestrator must be string[] with max length 5"
    if not all(isinstance(x, str) for x in notes) or len(notes) > 5:
        return False, "R-PO-001", "result.notes_for_orchestrator must be string[] with max length 5"

    # Done status requires acceptance checks
    if result.get("status") == "done":
        acceptance_check = result.get("acceptance_check")
        if not isinstance(acceptance_check, list) or len(acceptance_check) == 0:
            return False, "R-PC-001", "done status requires non-empty acceptance_check"

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


def validate_change(change: dict, idx: int) -> tuple[bool, str, str, dict | None]:
    """Validate structure of a single change entry."""
    if not isinstance(change, dict):
        return False, "R-PO-001", "result.changes entries must be objects", {"index": idx}

    resource = change.get("resource")
    action = change.get("action")

    if not isinstance(resource, str):
        return False, "R-PO-001", "result.changes.resource must be string", {"index": idx}
    if not isinstance(action, str) or not action.strip():
        return False, "R-PO-001", "result.changes.action must be non-empty string", {"index": idx}

    return True, "", "", None


def validate_scope_enforcement(
    changes: list,
    lock_scope_raw: list[str],
    forbidden_scope_raw: list[str],
) -> tuple[bool, str, str, dict | None]:
    """Validate all changes are within lock_scope and not in forbidden_scope."""
    # Normalize scopes
    lock_scope, code, reason, details = normalize_scope(lock_scope_raw, "R-PO-001", "assignment.lock_scope")
    if code is not None:
        return False, code, reason or "", details

    forbidden_scope, code, reason, details = normalize_scope(
        forbidden_scope_raw, "R-PO-001", "assignment.forbidden_scope"
    )
    if code is not None:
        return False, code, reason or "", details

    # Validate each change
    for idx, change in enumerate(changes):
        valid, code, reason, details = validate_change(change, idx)
        if not valid:
            return False, code, reason, details

        normalized_resource = normalize_resource(change["resource"])
        if not normalized_resource:
            return False, "R-PO-001", "result.changes.resource contains empty resource after normalization", {
                "index": idx,
                "resource": change["resource"],
            }

        # Check within lock_scope
        if not any(within(normalized_resource, scope) for scope in lock_scope):
            return False, "R-PO-002", "Changed file outside lock_scope", {
                "index": idx,
                "resource": normalized_resource,
            }

        # Check not in forbidden_scope
        for forbidden in forbidden_scope:
            if overlaps(normalized_resource, forbidden):
                return False, "R-PW-002", "Changed file in forbidden_scope", {
                    "index": idx,
                    "resource": normalized_resource,
                    "forbidden_scope": forbidden,
                }

    return True, "", "", None


def detect_secrets(notes: list[str]) -> bool:
    """Check notes_for_orchestrator for sensitive content."""
    patterns = [
        r"AKIA[0-9A-Z]{16}",  # AWS access key
        r"sk-ant-[A-Za-z0-9-]{20,}",  # Anthropic API key
        r"sk-[A-Za-z0-9]{20,}",  # OpenAI API key
        r"BEGIN [A-Z ]*PRIVATE KEY",  # Private key block
    ]

    # Separate case-insensitive pattern for generic secrets
    generic_secret_pattern = re.compile(r"(api[_-]?key|secret|token)\s*[:=]\s*\S+", re.IGNORECASE)

    combined = "|".join(patterns)
    regex = re.compile(combined)

    for note in notes:
        if isinstance(note, str):
            if regex.search(note) or generic_secret_pattern.search(note):
                return True
    return False


def main() -> int:
    """Main validation logic."""
    payload = json.load(sys.stdin)

    # Schema validation
    valid, code, reason = validate_schema(payload)
    if not valid:
        return emit(False, code, reason)

    # Scope enforcement
    result = payload["result"]
    assignment = payload["assignment"]
    valid, code, reason, details = validate_scope_enforcement(
        result["changes"],
        assignment["lock_scope"],
        assignment["forbidden_scope"],
    )
    if not valid:
        return emit(False, code, reason, details)

    # Worklog file existence
    worklog_path = result["worklog_path"]
    if not os.path.isfile(worklog_path):
        return emit(False, "R-PO-003", f"Worklog file missing: {worklog_path}")

    # Secret detection
    if detect_secrets(result.get("notes_for_orchestrator", [])):
        return emit(False, "R-PO-004", "Sensitive content detected in notes_for_orchestrator")

    return emit(True, "OK", "Validation passed")


if __name__ == "__main__":
    sys.exit(main())
