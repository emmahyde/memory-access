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

# Payload is expected to be an array of lock records.
echo "$payload" | jq -e 'type == "array"' >/dev/null || fail "R-LK-001" "Lock table must be an array"

# Detect exact scope overlaps among active tasks.
overlap=$(echo "$payload" | jq -r '
  [ .[] | select(.status == "in_progress") ] as $active
  | [ range(0; $active|length) as $i
      | range($i + 1; $active|length) as $j
      | $active[$i] as $a
      | $active[$j] as $b
      | ($a.lock_scope[]?) as $p
      | select(($b.lock_scope | index($p)) != null)
      | {path:$p, a:$a.task_id, b:$b.task_id}
    ]
  | .[0] // empty
')

if [ -n "$overlap" ]; then
  fail "R-LK-001" "Overlapping active locks detected: $overlap"
fi

pass
