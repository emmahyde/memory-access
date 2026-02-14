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

for f in task_id result assignment changed_files; do
  echo "$payload" | jq -e --arg f "$f" '.[$f] != null' >/dev/null || fail "R-PO-001" "Missing required field: $f"
done

for f in status changes acceptance_check worklog_path; do
  echo "$payload" | jq -e --arg f "$f" '.result[$f] != null' >/dev/null || fail "R-PO-001" "Missing result field: $f"
done

# Ensure every changed file is within lock_scope.
out_of_scope=$(echo "$payload" | jq -r '
  . as $root
  | [ $root.changed_files[] as $f
      | select((any($root.assignment.lock_scope[]?; . == $f)) | not)
      | $f
    ]
  | .[0] // empty
')

if [ -n "$out_of_scope" ]; then
  fail "R-PO-002" "Changed file outside lock_scope: $out_of_scope"
fi

# Ensure no changed file is in forbidden_scope
forbidden=$(echo "$payload" | jq -r '
  . as $root
  | [ $root.changed_files[] as $f
      | select(any($root.assignment.forbidden_scope[]?; . == $f))
      | $f
    ]
  | .[0] // empty
')

if [ -n "$forbidden" ]; then
  fail "R-PW-002" "Changed file in forbidden_scope: $forbidden"
fi

worklog=$(echo "$payload" | jq -r '.result.worklog_path')
[ -f "$worklog" ] || fail "R-PO-003" "Worklog file missing: $worklog"

pass
