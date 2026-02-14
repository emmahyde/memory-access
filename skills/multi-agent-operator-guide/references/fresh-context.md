# Fresh Context

Protocol for executing runs without dependence on prior conversation history.

## Objective

Start a new agent/session that can continue work deterministically from artifacts only.

## Required Inputs

1. `assets/handoff-template.json` filled for current run
2. `references/contracts.md`
3. `references/error-codes.md`
4. role prompt reference for active role

## Handoff Bundle Requirements

Handoff bundle MUST include:

- `schema_version`
- `run_id`
- `objective`
- `constraints`
- `ledger`
- `active_locks`
- `dependencies`
- `open_blockers`
- `acceptance_targets`

Each `ledger[]` task entry MUST include:

- `timeout_seconds`
- `heartbeat_interval_seconds`
- `priority`
- `last_heartbeat_at` (nullable when task has not started)

## Session Reset Protocol

1. Clear prior assumptions; do not rely on previous chat steps.
2. Load handoff bundle and validate structure.
3. Validate each assignment packet before dispatch.
4. Validate each subagent result before integration.
5. Run ledger reconciliation before closing tasks.

## Crash Recovery Protocol

Use when orchestrator process/session restarts mid-run:

1. Reload canonical `ledger`, `active_locks`, and recent task events from durable storage.
2. Re-run lock overlap validation and ledger reconciliation.
3. For each `in_progress` task, evaluate heartbeat timeout before redispatch.
4. Transition timed-out tasks to `blocked` with `TASK_TIMEOUT`, release locks, then replan.
5. Emit explicit recovery event with resumed `run_id` context.

## Determinism Rules

- Same validated handoff + same inputs should produce stable control-plane decisions.
- Use explicit error codes; avoid free-form failure categories.
- Persist run metadata (`run_id`, timestamps, actor ids) for traceability.
- Prefer blocking `wait for output` primitives for idle orchestrator periods; avoid high-frequency polling loops.

## Minimal Start Checklist

- [ ] handoff bundle loaded
- [ ] schema version supported
- [ ] active locks conflict-free
- [ ] outstanding blockers enumerated
- [ ] next assignment packet validated
