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

for f in task_id acceptance_check required_criteria; do
  echo "$payload" | jq -e --arg f "$f" '.[$f] != null' >/dev/null || fail "R-PC-001" "Missing required field: $f"
done

# Every required criterion must exist in acceptance_check
missing=$(echo "$payload" | jq -r '
  [ .required_criteria[] as $rc
    | select((.acceptance_check | map(.criterion) | index($rc)) == null)
  ] | .[0] // empty
')

if [ -n "$missing" ]; then
  fail "R-PC-001" "Missing acceptance criterion: $missing"
fi

# Every criterion must pass
failed=$(echo "$payload" | jq -r '
  [ .acceptance_check[] | select(.status != "pass") | .criterion ] | .[0] // empty
')
if [ -n "$failed" ]; then
  fail "R-PC-002" "Acceptance failed: $failed"
fi

# Every criterion must include non-empty evidence
no_evidence=$(echo "$payload" | jq -r '
  [ .acceptance_check[]
    | select((.evidence | type != "string") or (.evidence | length == 0))
    | .criterion
  ] | .[0] // empty
')
if [ -n "$no_evidence" ]; then
  fail "R-PC-003" "Missing evidence for criterion: $no_evidence"
fi

pass
