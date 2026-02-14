#!/bin/bash
set -euo pipefail

payload=$(cat)

STATE="INIT"
now_epoch=""
timed_out_json="[]"

emit_allow() {
  local code="$1"
  local reason="$2"
  local details="${3:-}"
  if [ -n "$details" ]; then
    jq -cn --arg code "$code" --arg reason "$reason" --argjson details "$details" \
      '{allow:true, code:$code, reason:$reason, details:$details}'
  else
    jq -cn --arg code "$code" --arg reason "$reason" \
      '{allow:true, code:$code, reason:$reason}'
  fi
  exit 0
}

emit_deny() {
  local code="$1"
  local reason="$2"
  local details="${3:-}"
  if [ -n "$details" ]; then
    jq -cn --arg code "$code" --arg reason "$reason" --argjson details "$details" \
      '{allow:false, code:$code, reason:$reason, details:$details}'
  else
    jq -cn --arg code "$code" --arg reason "$reason" \
      '{allow:false, code:$code, reason:$reason}'
  fi
  exit 1
}

epoch_from_iso() {
  local ts="$1"
  python3 - "$ts" <<'PY'
import datetime as dt
import sys

value = sys.argv[1]
if value.endswith("Z"):
    value = value[:-1] + "+00:00"
parsed = dt.datetime.fromisoformat(value)
if parsed.tzinfo is None:
    parsed = parsed.replace(tzinfo=dt.timezone.utc)
print(int(parsed.timestamp()))
PY
}

while :; do
  case "$STATE" in
    INIT)
      STATE="VALIDATE_PAYLOAD"
      ;;
    VALIDATE_PAYLOAD)
      echo "$payload" | jq -e 'type == "object"' >/dev/null || emit_deny "SCHEMA_INVALID" "payload must be object"
      echo "$payload" | jq -e '.now | type == "string" and length > 0' >/dev/null \
        || emit_deny "MISSING_REQUIRED_INPUT" "missing required field: now"
      echo "$payload" | jq -e '.tasks | type == "array"' >/dev/null \
        || emit_deny "MISSING_REQUIRED_INPUT" "missing required field: tasks"
      if ! now_epoch=$(epoch_from_iso "$(echo "$payload" | jq -r '.now')" 2>/dev/null); then
        emit_deny "SCHEMA_INVALID" "now must be ISO-8601 timestamp"
      fi
      STATE="SCAN_TASKS"
      ;;
    SCAN_TASKS)
      while IFS= read -r task; do
        status=$(echo "$task" | jq -r '.status // ""')
        [ "$status" = "in_progress" ] || continue

        task_id=$(echo "$task" | jq -r '.task_id // ""')
        timeout_seconds=$(echo "$task" | jq -r '.timeout_seconds // empty')
        heartbeat_at=$(echo "$task" | jq -r '.last_heartbeat_at // empty')

        [ -n "$task_id" ] || emit_deny "SCHEMA_INVALID" "in_progress task missing task_id"
        [[ "$timeout_seconds" =~ ^[0-9]+$ ]] || emit_deny "SCHEMA_INVALID" "timeout_seconds must be integer for in_progress tasks"
        [ "$timeout_seconds" -ge 30 ] || emit_deny "SCHEMA_INVALID" "timeout_seconds must be >= 30 for in_progress tasks"
        [ -n "$heartbeat_at" ] || emit_deny "SCHEMA_INVALID" "last_heartbeat_at required for in_progress tasks"

        if ! heartbeat_epoch=$(epoch_from_iso "$heartbeat_at" 2>/dev/null); then
          emit_deny "SCHEMA_INVALID" "last_heartbeat_at must be ISO-8601 timestamp"
        fi

        age=$((now_epoch - heartbeat_epoch))
        if [ "$age" -lt -30 ]; then
          emit_deny "R-WD-002" "last_heartbeat_at is in the future beyond allowed clock skew"
        fi
        if [ "$age" -gt "$timeout_seconds" ]; then
          timed_out_json=$(jq -cn \
            --argjson prior "$timed_out_json" \
            --arg task_id "$task_id" \
            --arg last_heartbeat_at "$heartbeat_at" \
            --argjson timeout_seconds "$timeout_seconds" \
            --argjson age_seconds "$age" \
            '$prior + [{task_id:$task_id,last_heartbeat_at:$last_heartbeat_at,timeout_seconds:$timeout_seconds,age_seconds:$age_seconds}]')
        fi
      done < <(echo "$payload" | jq -c '.tasks[]')
      STATE="DECIDE"
      ;;
    DECIDE)
      if [ "$(echo "$timed_out_json" | jq 'length')" -gt 0 ]; then
        timeout_details=$(jq -cn --argjson timed_out "$timed_out_json" '{timed_out:$timed_out}')
        emit_deny "R-WD-001" "task heartbeat exceeded timeout" "$timeout_details"
      fi
      emit_allow "OK" "watchdog check passed" '{"timed_out_count":0}'
      ;;
    *)
      emit_deny "NON_COMPLIANT" "invalid internal state: $STATE"
      ;;
  esac
done
