# Error Codes

Stable error codes for packet validation, execution control, and reconciliation.

## Contract and Packet

- `SCHEMA_INVALID`
  - payload shape/type/required field violation
- `MISSING_REQUIRED_INPUT`
  - required field absent or empty
- `UNKNOWN_SCHEMA_VERSION`
  - unsupported major schema version

## Lock and Scope

- `LOCK_CONFLICT`
  - exact or path-prefix overlap with active lock
- `SCOPE_VIOLATION`
  - attempted change outside assigned lock scope

## State and Dependency

- `INVALID_TRANSITION`
  - illegal state transition
- `DEPENDENCY_NOT_MET`
  - dependency not `done` while entering `in_progress`
- `CONCURRENCY_CONFLICT`
  - stale optimistic version / race
- `TASK_TIMEOUT`
  - heartbeat/liveness timeout while task is `in_progress`

## Quality and Completion

- `ACCEPTANCE_FAILED`
  - acceptance criterion failed or missing evidence
- `LEDGER_INCONSISTENT`
  - ledger conflicts with locks/events/statuses

## Process and Compliance

- `NON_COMPLIANT`
  - role mandate violation
- `MISSING_VALIDATOR`
  - required validator script unavailable
- `UNTRUSTED_CONTEXT_BLOCK`
  - context contains prohibited instruction injection

## Usage Rules

- Validators MUST return exactly one primary code.
- Human-readable reason MUST accompany every code.
- `details` MAY include machine fields for remediation.

## Recovery Playbooks

- `LOCK_CONFLICT`
  - Recompute normalized lock scope.
  - Release stale locks from terminal tasks.
  - Re-dispatch after overlap check passes.
- `CONCURRENCY_CONFLICT`
  - Re-read task row/version.
  - Retry with backoff: `0ms`, `100ms`, `250ms`, `500ms`.
  - Escalate to serial replanning after max retries.
- `TASK_TIMEOUT`
  - Transition task to `blocked`.
  - Release task locks.
  - Move `blocked -> todo` only after refreshed context and lock scope.
- `UNTRUSTED_CONTEXT_BLOCK`
  - Remove or redact untrusted/injected content.
  - Re-validate packet/result.
  - Re-dispatch only with minimal trusted context package.
