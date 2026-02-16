# End-to-End Worked Example

This directory contains a fully populated example flow with validator outputs.

## Files

- `01-assignment-valid.json`
- `01-assignment-invalid-empty-normalized-lock.json`
- `01-assignment-invalid-dependency-id.json`
- `02-locks-valid.json`
- `02-locks-conflict.json`
- `03-result-valid.json`
- `03-result-invalid-empty-acceptance.json`
- `03-result-invalid-secret-note.json`
- `04-reconcile-valid.json`
- `05-e2e-success-trace.output.json`
- `06-e2e-timeout-recovery-trace.output.json`
- `*.output.json` files: captured validator outputs

## Step-by-Step

Run from repository root:

```bash
python3 skills/multi-agent-operator-guide/scripts/validate_packet.py < skills/multi-agent-operator-guide/examples/01-assignment-valid.json
python3 skills/multi-agent-operator-guide/scripts/validate_packet.py < skills/multi-agent-operator-guide/examples/01-assignment-invalid-empty-normalized-lock.json
python3 skills/multi-agent-operator-guide/scripts/validate_packet.py < skills/multi-agent-operator-guide/examples/01-assignment-invalid-dependency-id.json
python3 skills/multi-agent-operator-guide/scripts/check_lock_overlap.py < skills/multi-agent-operator-guide/examples/02-locks-valid.json
python3 skills/multi-agent-operator-guide/scripts/check_lock_overlap.py < skills/multi-agent-operator-guide/examples/02-locks-conflict.json
python3 skills/multi-agent-operator-guide/scripts/validate_result.py < skills/multi-agent-operator-guide/examples/03-result-valid.json
python3 skills/multi-agent-operator-guide/scripts/validate_result.py < skills/multi-agent-operator-guide/examples/03-result-invalid-empty-acceptance.json
python3 skills/multi-agent-operator-guide/scripts/validate_result.py < skills/multi-agent-operator-guide/examples/03-result-invalid-secret-note.json
python3 skills/multi-agent-operator-guide/scripts/reconcile_ledger.py < skills/multi-agent-operator-guide/examples/04-reconcile-valid.json
uv run pytest tests/test_orchestrator_e2e.py -q
```

Compare each script command output with the corresponding `*.output.json` file.
The pytest command validates full orchestrator flows against:
- `05-e2e-success-trace.output.json`
- `06-e2e-timeout-recovery-trace.output.json`

## Expected Behavior

- Valid assignment/result/reconcile payloads return `{"allow":true,"code":"OK",...}`
- Empty normalized `lock_scope` is denied with `SCHEMA_INVALID`
- Invalid dependency identifiers are denied with `SCHEMA_INVALID`
- `status=done` with empty `acceptance_check` is denied with `ACCEPTANCE_FAILED`
- Secret-like content in `notes_for_orchestrator` is denied with `UNTRUSTED_CONTEXT_BLOCK`
- Path-prefix lock collisions are denied with `LOCK_CONFLICT`
- The success E2E flow shows assignment -> dispatch -> execution -> reconciliation -> watchdog pass
- The timeout E2E flow shows in-progress -> watchdog timeout -> blocked -> todo replanning
