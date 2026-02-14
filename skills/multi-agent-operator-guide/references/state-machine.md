# State Machine

Deterministic task lifecycle for orchestrator-led execution.

## States

- `todo`
- `in_progress`
- `blocked`
- `done`
- `failed`
- `canceled`

`done`, `failed`, and `canceled` are terminal.

## Legal Transitions

- `todo -> in_progress|blocked|failed|canceled`
- `in_progress -> done|blocked|failed|canceled`
- `blocked -> todo|in_progress|failed|canceled`
- `done -> done` (idempotent re-assert only)
- `failed -> failed` (idempotent re-assert only)
- `canceled -> canceled` (idempotent re-assert only)

All other transitions are invalid and MUST return `INVALID_TRANSITION`.

## Terminal Self-Loop Semantics

Terminal self-loop transitions are allowed only for replay and recovery idempotency.

Required behavior for terminal self-loop:

- MUST NOT acquire new locks
- MUST NOT change `owner`
- MUST NOT mutate acceptance artifacts
- MUST emit an append-only event describing replay reason

## Transition Preconditions

### Enter `in_progress`

Must satisfy all:

1. Task dependencies are `done`.
2. Lock scope is active and conflict-free.
3. Assignment packet validates.
4. Task owner is set.

### Enter `done`

Must satisfy all:

1. Result packet validates.
2. All acceptance criteria have `pass` with non-empty evidence.
3. Reconciliation reports no blocking inconsistencies.

### Enter `blocked`

Requires:

- explicit blocker `code` and `reason`
- blocker represented in orchestrator output `blockers[]`

## Timeout and Watchdog Protocol

Every assigned task MUST include:

- `timeout_seconds`
- `heartbeat_interval_seconds`

Watchdog behavior:

1. Orchestrator refreshes liveness at least every `heartbeat_interval_seconds`.
2. Subagent heartbeat MUST update `last_heartbeat_at`.
3. If `now - last_heartbeat_at > timeout_seconds`, task MUST transition to `blocked` with `TASK_TIMEOUT`.
4. Timeout transition MUST release active locks for that task before rescheduling.
5. Timeout event MUST include `task_id`, `last_heartbeat_at`, and `timeout_seconds`.

Scheduler behavior:

- Prefer blocking wait for worker output while idle.
- Avoid busy polling loops; wake on completion, timeout boundary, or cancel.
- On wake, re-validate state before applying transitions.

## Retry and Escalation Budget

Default policy:

- One retry per failed subagent attempt (`retry_budget = 1`).
- On second failure for same task/owner:
  - escalate model or
  - replan serially

Retry is forbidden when failure code is structural:

- `SCHEMA_INVALID`
- `SCOPE_VIOLATION`
- `NON_COMPLIANT`

These require packet/plan correction before re-dispatch.

## Replan Path

- `blocked -> todo` is the canonical transition for orchestrator replanning.
- Use it when blockers are resolved without concrete execution progress.
- Replan MUST refresh lock scope and context package before re-dispatch.

## Concurrency Rules

- Transitions SHOULD be applied with optimistic version checks.
- On stale version mismatch, return `CONCURRENCY_CONFLICT`.
- Orchestrator MUST re-read latest task row before retrying transition.
- Retry/backoff strategy for `CONCURRENCY_CONFLICT`:
  1. attempt 1 immediate retry after re-read
  2. attempt 2 after `100ms`
  3. attempt 3 after `250ms`
  4. attempt 4 after `500ms`
  5. if still failing, emit blocker and replan/serialize conflicting tasks

## Cancellation Rules

- `canceled` may be set from any non-terminal state.
- Canceling a task SHOULD release all active locks for that task.
- Canceled tasks MUST NOT be re-opened in the same run; create a new task id instead.

## Event Requirements

Every transition MUST emit an append-only event containing:

- `task_id`
- `from_state`
- `to_state`
- `actor`
- `reason`
- `created_at`
