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

# Payload is expected to be an array of lock records.
echo "$payload" | jq -e 'type == "array"' >/dev/null || fail "R-LK-001" "Lock table must be an array"

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


locks = json.loads(os.environ["PAYLOAD_JSON"])
normalized: list[dict[str, Any]] = []
for idx, lock in enumerate(locks):
    if not isinstance(lock, dict):
        deny("R-LK-001", "lock entries must be objects", {"index": idx})

    task_id = lock.get("task_id")
    resource = lock.get("resource")
    active = lock.get("active")
    if not isinstance(task_id, str) or not task_id:
        deny("R-LK-001", "lock.task_id must be non-empty string", {"index": idx})
    if not isinstance(resource, str):
        deny("R-LK-001", "lock.resource must be string", {"index": idx})
    if not isinstance(active, bool):
        deny("R-LK-001", "lock.active must be bool", {"index": idx})

    normalized_resource = normalize_resource(resource)
    if not normalized_resource:
        deny(
            "R-LK-001",
            "lock.resource contains empty resource after normalization",
            {"index": idx, "resource": resource},
        )

    normalized.append({"task_id": task_id, "resource": normalized_resource, "active": active})

active_locks = [lock for lock in normalized if lock["active"]]
for i in range(len(active_locks)):
    for j in range(i + 1, len(active_locks)):
        left = active_locks[i]
        right = active_locks[j]
        if left["task_id"] == right["task_id"]:
            continue
        if overlaps(left["resource"], right["resource"]):
            deny(
                "R-LK-001",
                "Overlapping active locks detected",
                {"a": left["task_id"], "b": right["task_id"], "resource_a": left["resource"], "resource_b": right["resource"]},
            )

print('{"allow":true,"code":"OK","reason":"lock table is conflict-free"}')
PY
)

if [ "$(echo "$policy" | jq -r '.allow')" != "true" ]; then
  fail "$(echo "$policy" | jq -r '.code')" "$(echo "$policy" | jq -r '.reason')" "$(echo "$policy" | jq -c '.details // empty')"
fi

pass
