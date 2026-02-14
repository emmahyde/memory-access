#!/bin/bash
set -euo pipefail

payload=$(cat)

fail() {
  local code="$1"
  local reason="$2"
  echo "{\"allow\":false,\"code\":\"$code\",\"reason\":\"$reason\"}"
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
for f in lock_scope forbidden_scope acceptance_criteria worklog_path; do
  echo "$payload" | jq -e --arg f "$f" '.assignment[$f] != null' >/dev/null || fail "R-PD-001" "Missing assignment field: $f"
done

# Non-empty lock scope
echo "$payload" | jq -e '.assignment.lock_scope | type == "array" and length > 0' >/dev/null || fail "R-PD-002" "lock_scope must be a non-empty array"

# Non-empty worklog path
echo "$payload" | jq -e '.assignment.worklog_path | type == "string" and length > 0' >/dev/null || fail "R-PD-005" "worklog_path is required"

# Active overlap detection by exact resource match against in-progress locks.
# (Path-prefix overlap can be layered in controller logic.)
overlap=$(echo "$payload" | jq -r '
  [ .assignment.lock_scope[] as $mine
    | .active_locks[]
    | select(.status == "in_progress")
    | .lock_scope[]
    | select(. == $mine)
  ] | unique | .[0] // empty
')

if [ -n "$overlap" ]; then
  fail "R-PD-003" "Lock overlap detected on: $overlap"
fi

pass
