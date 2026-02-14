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

for f in task_id result assignment; do
  echo "$payload" | jq -e --arg f "$f" '.[$f] != null' >/dev/null || fail "R-PO-001" "Missing required field: $f"
done

for f in status changes acceptance_check worklog_path notes_for_orchestrator; do
  echo "$payload" | jq -e --arg f "$f" '.result[$f] != null' >/dev/null || fail "R-PO-001" "Missing result field: $f"
done

# Done status requires acceptance checks.
echo "$payload" | jq -e 'if .result.status == "done" then (.result.acceptance_check | type == "array" and length > 0) else true end' >/dev/null \
  || fail "R-PC-001" "done status requires non-empty acceptance_check"

echo "$payload" | jq -e '.result.changes | type == "array"' >/dev/null || fail "R-PO-001" "result.changes must be an array"
echo "$payload" | jq -e '.assignment.lock_scope | type == "array" and all(type == "string") and length > 0' >/dev/null \
  || fail "R-PO-001" "assignment.lock_scope must be non-empty string[]"
echo "$payload" | jq -e '.assignment.forbidden_scope | type == "array" and all(type == "string")' >/dev/null \
  || fail "R-PO-001" "assignment.forbidden_scope must be string[]"
echo "$payload" | jq -e '.result.notes_for_orchestrator | type == "array" and all(type == "string") and length <= 5' >/dev/null \
  || fail "R-PO-001" "result.notes_for_orchestrator must be string[] with max length 5"

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


def within(candidate: str, scope: str) -> bool:
    return candidate == scope or candidate.startswith(scope + "/")


def deny(code: str, reason: str, details: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"allow": False, "code": code, "reason": reason}
    if details:
        payload["details"] = details
    print(json.dumps(payload, separators=(",", ":")))
    raise SystemExit(0)


payload = json.loads(os.environ["PAYLOAD_JSON"])
changes = payload.get("result", {}).get("changes", [])
lock_scope_raw = payload.get("assignment", {}).get("lock_scope", [])
forbidden_scope_raw = payload.get("assignment", {}).get("forbidden_scope", [])

normalized_scope: list[str] = []
for idx, resource in enumerate(lock_scope_raw):
    normalized = normalize_resource(resource)
    if not normalized:
        deny(
            "R-PO-001",
            "assignment.lock_scope contains empty resource after normalization",
            {"index": idx, "resource": resource},
        )
    normalized_scope.append(normalized)

normalized_forbidden: list[str] = []
for idx, resource in enumerate(forbidden_scope_raw):
    normalized = normalize_resource(resource)
    if not normalized:
        deny(
            "R-PO-001",
            "assignment.forbidden_scope contains empty resource after normalization",
            {"index": idx, "resource": resource},
        )
    normalized_forbidden.append(normalized)

for idx, change in enumerate(changes):
    if not isinstance(change, dict):
        deny("R-PO-001", "result.changes entries must be objects", {"index": idx})

    resource = change.get("resource")
    action = change.get("action")
    if not isinstance(resource, str):
        deny("R-PO-001", "result.changes.resource must be string", {"index": idx})
    if not isinstance(action, str) or not action.strip():
        deny("R-PO-001", "result.changes.action must be non-empty string", {"index": idx})

    normalized_resource = normalize_resource(resource)
    if not normalized_resource:
        deny(
            "R-PO-001",
            "result.changes.resource contains empty resource after normalization",
            {"index": idx, "resource": resource},
        )

    if not any(within(normalized_resource, own_scope) for own_scope in normalized_scope):
        deny(
            "R-PO-002",
            "Changed file outside lock_scope",
            {"index": idx, "resource": normalized_resource},
        )

    for forbidden in normalized_forbidden:
        if overlaps(normalized_resource, forbidden):
            deny(
                "R-PW-002",
                "Changed file in forbidden_scope",
                {"index": idx, "resource": normalized_resource, "forbidden_scope": forbidden},
            )

print('{"allow":true,"code":"OK","reason":"scope checks passed"}')
PY
)

if [ "$(echo "$policy" | jq -r '.allow')" != "true" ]; then
  fail "$(echo "$policy" | jq -r '.code')" "$(echo "$policy" | jq -r '.reason')" "$(echo "$policy" | jq -c '.details // empty')"
fi

worklog=$(echo "$payload" | jq -r '.result.worklog_path')
[ -f "$worklog" ] || fail "R-PO-003" "Worklog file missing: $worklog"

# Guard notes_for_orchestrator as a potential exfil channel.
secret_note=$(echo "$payload" | jq -r '
  (.result.notes_for_orchestrator // [])
  | map(select(type == "string"))
  | map(select(test("AKIA[0-9A-Z]{16}|sk-ant-[A-Za-z0-9-]{20,}|sk-[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY|(?i)(api[_-]?key|secret|token)\\s*[:=]\\s*\\S+")))
  | .[0] // empty
')

if [ -n "$secret_note" ]; then
  fail "R-PO-004" "Sensitive content detected in notes_for_orchestrator"
fi

pass
