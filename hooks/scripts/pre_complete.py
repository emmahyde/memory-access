#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
"""Validates pre-completion acceptance checks."""

from __future__ import annotations

import json
import sys


def emit(allow: bool, code: str, reason: str, details: dict | None = None) -> int:
    """Emit validation result as JSON to stdout."""
    payload = {"allow": allow, "code": code, "reason": reason}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if allow else 1


def validate_required_fields(payload: dict) -> tuple[bool, str, str]:
    """Validate that all required fields are present."""
    for field in ["task_id", "acceptance_check", "required_criteria"]:
        if field not in payload:
            return False, "R-PC-001", f"Missing required field: {field}"
    return True, "", ""


def find_missing_criterion(payload: dict) -> str | None:
    """Find first required criterion missing from acceptance_check."""
    acceptance_criteria = {entry.get("criterion") for entry in payload["acceptance_check"]}
    for required in payload["required_criteria"]:
        if required not in acceptance_criteria:
            return required
    return None


def find_failed_criterion(payload: dict) -> str | None:
    """Find first acceptance check entry that doesn't have status='pass'."""
    for entry in payload["acceptance_check"]:
        if entry.get("status") != "pass":
            return entry.get("criterion")
    return None


def find_missing_evidence(payload: dict) -> str | None:
    """Find first acceptance check entry with missing or empty evidence."""
    for entry in payload["acceptance_check"]:
        evidence = entry.get("evidence")
        if not isinstance(evidence, str) or len(evidence) == 0:
            return entry.get("criterion")
    return None


def main() -> int:
    """Main validation logic."""
    payload = json.load(sys.stdin)

    # Check required fields
    valid, code, reason = validate_required_fields(payload)
    if not valid:
        return emit(False, code, reason)

    # Check all required criteria are in acceptance_check
    missing_criterion = find_missing_criterion(payload)
    if missing_criterion:
        return emit(False, "R-PC-001", f"Missing acceptance criterion: {missing_criterion}")

    # Check all criteria have status=pass
    failed_criterion = find_failed_criterion(payload)
    if failed_criterion:
        return emit(False, "R-PC-002", f"Acceptance failed: {failed_criterion}")

    # Check all criteria have evidence
    no_evidence = find_missing_evidence(payload)
    if no_evidence:
        return emit(False, "R-PC-003", f"Missing evidence for criterion: {no_evidence}")

    return emit(True, "OK", "Validation passed")


if __name__ == "__main__":
    sys.exit(main())
