#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from typing import Any

RUN_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")
TASK_ID_RE = re.compile(r"^(T-[0-9]+|[0-9a-fA-F-]{36})$")
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("anthropic_api_key", re.compile(r"\bsk-ant-[A-Za-z0-9-]{20,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("generic_secret_assignment", re.compile(r"(?i)\b(api[_-]?key|secret|token)\b\s*[:=]\s*\S+")),
]


def emit(allow: bool, code: str, reason: str, details: dict[str, Any] | None = None) -> int:
    payload: dict[str, Any] = {"allow": allow, "code": code, "reason": reason}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")))
    return 0 if allow else 1


def validate_schema_version(value: Any) -> tuple[bool, str]:
    if not isinstance(value, str) or not value:
        return False, "schema_version must be a non-empty string"
    major = value.split(".", 1)[0]
    if major != "1":
        return False, f"unsupported schema major version: {value}"
    return True, ""


def detect_secret(value: str) -> str | None:
    for pattern_name, pattern in SECRET_PATTERNS:
        if pattern.search(value):
            return pattern_name
    return None


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        return emit(False, "SCHEMA_INVALID", "empty stdin payload")

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        return emit(False, "SCHEMA_INVALID", "invalid JSON", {"error": str(exc)})

    if not isinstance(result, dict):
        return emit(False, "SCHEMA_INVALID", "top-level payload must be an object")

    required = [
        "schema_version",
        "run_id",
        "task_id",
        "status",
        "changes",
        "acceptance_check",
        "worklog_path",
        "notes_for_orchestrator",
    ]
    missing = [key for key in required if key not in result]
    if missing:
        return emit(False, "MISSING_REQUIRED_INPUT", "missing required fields", {"missing": missing})

    ok, msg = validate_schema_version(result["schema_version"])
    if not ok:
        return emit(False, "UNKNOWN_SCHEMA_VERSION", msg)

    if not isinstance(result["run_id"], str) or not RUN_ID_RE.match(result["run_id"]):
        return emit(False, "SCHEMA_INVALID", "run_id must be UUID-like")

    if not isinstance(result["task_id"], str) or not TASK_ID_RE.match(result["task_id"]):
        return emit(False, "SCHEMA_INVALID", "task_id must match expected format")

    if result["status"] not in {"done", "blocked", "failed"}:
        return emit(False, "SCHEMA_INVALID", "status must be done|blocked|failed")

    if not isinstance(result["worklog_path"], str) or not result["worklog_path"].strip():
        return emit(False, "MISSING_REQUIRED_INPUT", "worklog_path must be non-empty")

    changes = result["changes"]
    if not isinstance(changes, list):
        return emit(False, "SCHEMA_INVALID", "changes must be an array")

    for idx, item in enumerate(changes):
        if not isinstance(item, dict):
            return emit(False, "SCHEMA_INVALID", "changes entries must be objects", {"index": idx})
        resource = item.get("resource")
        action = item.get("action")
        if not isinstance(resource, str) or not resource.strip():
            return emit(False, "SCHEMA_INVALID", "changes.resource must be non-empty string", {"index": idx})
        if not isinstance(action, str) or not action.strip():
            return emit(False, "SCHEMA_INVALID", "changes.action must be non-empty string", {"index": idx})

    acceptance = result["acceptance_check"]
    if not isinstance(acceptance, list):
        return emit(False, "SCHEMA_INVALID", "acceptance_check must be an array")

    for idx, item in enumerate(acceptance):
        if not isinstance(item, dict):
            return emit(False, "SCHEMA_INVALID", "acceptance_check entries must be objects", {"index": idx})
        criterion = item.get("criterion")
        status = item.get("status")
        evidence = item.get("evidence")
        if not isinstance(criterion, str) or not criterion.strip():
            return emit(False, "SCHEMA_INVALID", "acceptance_check.criterion must be non-empty string", {"index": idx})
        if status not in {"pass", "fail"}:
            return emit(False, "SCHEMA_INVALID", "acceptance_check.status must be pass|fail", {"index": idx})
        if not isinstance(evidence, str) or not evidence.strip():
            return emit(False, "SCHEMA_INVALID", "acceptance_check.evidence must be non-empty string", {"index": idx})

    notes = result["notes_for_orchestrator"]
    if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
        return emit(False, "SCHEMA_INVALID", "notes_for_orchestrator must be string[]")
    if len(notes) > 5:
        return emit(False, "SCHEMA_INVALID", "notes_for_orchestrator length must be <= 5")
    for idx, note in enumerate(notes):
        if not note.strip():
            return emit(False, "SCHEMA_INVALID", "notes_for_orchestrator entries must be non-empty strings", {"index": idx})
        secret_pattern = detect_secret(note)
        if secret_pattern:
            return emit(
                False,
                "UNTRUSTED_CONTEXT_BLOCK",
                "notes_for_orchestrator contains possible secret material",
                {"index": idx, "pattern": secret_pattern},
            )

    if result["status"] == "done":
        if not acceptance:
            return emit(False, "ACCEPTANCE_FAILED", "done result requires non-empty acceptance_check")
        failing = [item["criterion"] for item in acceptance if item.get("status") != "pass"]
        if failing:
            return emit(
                False,
                "ACCEPTANCE_FAILED",
                "done result includes failing acceptance criteria",
                {"failing_criteria": failing},
            )

    return emit(True, "OK", "result packet valid")


if __name__ == "__main__":
    raise SystemExit(main())
