#!/bin/bash
set -euo pipefail

payload=$(cat)

fail() {
  local code="$1"
  local reason="$2"
  local details="${3:-}"
  if [ -n "$details" ]; then
    echo "{\"allow\":false,\"code\":\"$code\",\"reason\":\"$reason\",\"details\":$details}"
  else
    echo "{\"allow\":false,\"code\":\"$code\",\"reason\":\"$reason\"}"
  fi
  exit 1
}

pass() {
  echo '{"allow":true,"code":"OK","reason":"Validation passed"}'
}

# Required top-level fields
for f in task_id assignment active_locks; do
  echo "$payload" | jq -e --arg f "$f" '.[$f] != null' >/dev/null || fail "R-PD-001" "Missing required field: $f"
done

# Required assignment fields
for f in lock_scope forbidden_scope acceptance_criteria worklog_path timeout_seconds heartbeat_interval_seconds; do
  echo "$payload" | jq -e --arg f "$f" '.assignment[$f] != null' >/dev/null || fail "R-PD-001" "Missing assignment field: $f"
done

# Non-empty lock scope
echo "$payload" | jq -e '.assignment.lock_scope | type == "array" and length > 0' >/dev/null || fail "R-PD-002" "lock_scope must be a non-empty array"
echo "$payload" | jq -e '.assignment.lock_scope | all(type == "string")' >/dev/null || fail "R-PD-002" "lock_scope entries must be strings"
echo "$payload" | jq -e '.assignment.forbidden_scope | type == "array" and all(type == "string")' >/dev/null || fail "R-PD-004" "forbidden_scope must be string[]"
echo "$payload" | jq -e '.assignment.acceptance_criteria | type == "array" and length > 0 and all(type == "string" and length > 0)' >/dev/null \
  || fail "R-PD-001" "acceptance_criteria must be non-empty string[]"
echo "$payload" | jq -e '.active_locks | type == "array"' >/dev/null || fail "R-PD-007" "active_locks must be an array"

# Non-empty worklog path
echo "$payload" | jq -e '.assignment.worklog_path | type == "string" and length > 0' >/dev/null || fail "R-PD-005" "worklog_path is required"

# Timeout and heartbeat liveness controls
echo "$payload" | jq -e '.assignment.timeout_seconds | type == "number" and . >= 30 and (. % 1 == 0)' >/dev/null \
  || fail "R-PD-006" "timeout_seconds must be an integer >= 30"
echo "$payload" | jq -e '.assignment.heartbeat_interval_seconds | type == "number" and . >= 5 and (. % 1 == 0)' >/dev/null \
  || fail "R-PD-006" "heartbeat_interval_seconds must be an integer >= 5"
echo "$payload" | jq -e '.assignment.heartbeat_interval_seconds < .assignment.timeout_seconds' >/dev/null \
  || fail "R-PD-006" "heartbeat_interval_seconds must be less than timeout_seconds"

# Canonical lock checks with path-prefix semantics.
policy=$(PAYLOAD_JSON="$payload" python3 - <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import PurePosixPath
from typing import Any


def normalize_resource(value: str) -> str:
    resource = value.strip().replace("\\", "/")
    if not resource:
        return ""
    normalized = str(PurePosixPath(resource))
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized


def overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def deny(code: str, reason: str, details: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"allow": False, "code": code, "reason": reason}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")))
    raise SystemExit(0)


payload = json.loads(os.environ["PAYLOAD_JSON"])
task_id = payload.get("task_id", "")
assignment = payload.get("assignment", {})
lock_scope_raw = assignment.get("lock_scope", [])
forbidden_scope_raw = assignment.get("forbidden_scope", [])
active_locks = payload.get("active_locks", [])

normalized_scope: list[str] = []
for idx, resource in enumerate(lock_scope_raw):
    normalized = normalize_resource(resource)
    if not normalized:
        deny(
            "R-PD-002",
            "lock_scope contains empty resource after normalization",
            {"index": idx, "resource": resource},
        )
    normalized_scope.append(normalized)

normalized_forbidden: list[str] = []
for idx, resource in enumerate(forbidden_scope_raw):
    normalized = normalize_resource(resource)
    if not normalized:
        deny(
            "R-PD-004",
            "forbidden_scope contains empty resource after normalization",
            {"index": idx, "resource": resource},
        )
    normalized_forbidden.append(normalized)

for i in range(len(normalized_scope)):
    for j in range(i + 1, len(normalized_scope)):
        if overlaps(normalized_scope[i], normalized_scope[j]):
            deny(
                "R-PD-003",
                "lock_scope contains overlapping resources",
                {"a": normalized_scope[i], "b": normalized_scope[j]},
            )

for own in normalized_scope:
    for forbidden in normalized_forbidden:
        if overlaps(own, forbidden):
            deny(
                "R-PD-004",
                "forbidden_scope overlaps lock_scope",
                {"lock_scope": own, "forbidden_scope": forbidden},
            )

for idx, lock in enumerate(active_locks):
    if not isinstance(lock, dict):
        deny("R-PD-007", "active_locks entries must be objects", {"index": idx})

    lock_task_id = lock.get("task_id")
    resource = lock.get("resource")
    active = lock.get("active")

    if not isinstance(lock_task_id, str) or not lock_task_id:
        deny("R-PD-007", "active_locks.task_id must be non-empty string", {"index": idx})
    if not isinstance(resource, str):
        deny("R-PD-007", "active_locks.resource must be string", {"index": idx})
    if not isinstance(active, bool):
        deny("R-PD-007", "active_locks.active must be bool", {"index": idx})

    if not active or lock_task_id == task_id:
        continue

    normalized_active = normalize_resource(resource)
    if not normalized_active:
        deny(
            "R-PD-007",
            "active_locks.resource contains empty resource after normalization",
            {"index": idx, "resource": resource},
        )
    for own in normalized_scope:
        if overlaps(own, normalized_active):
            deny(
                "R-PD-003",
                "assignment lock_scope conflicts with active lock",
                {
                    "task_id": task_id,
                    "resource": own,
                    "conflict_task_id": lock_task_id,
                    "conflict_resource": normalized_active,
                },
            )

print('{"allow":true,"code":"OK","reason":"policy checks passed"}')
PY
)

if [ "$(echo "$policy" | jq -r '.allow')" != "true" ]; then
  fail "$(echo "$policy" | jq -r '.code')" "$(echo "$policy" | jq -r '.reason')" "$(echo "$policy" | jq -c '.details // empty')"
fi

pass
