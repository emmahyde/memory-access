# Task State Machine Runbook

Operational guide for the SQLite-backed task state machine used by `memory-access`.

## Scope

This runbook covers:
- Task lifecycle transitions
- Lock and dependency troubleshooting
- Validation queries
- Migration verification

## Lifecycle

Allowed states:
- `todo`
- `in_progress`
- `blocked`
- `done`
- `failed`
- `canceled`

Allowed transitions are DB-enforced by trigger:
- `todo -> in_progress|blocked|failed|canceled`
- `in_progress -> done|blocked|failed|canceled`
- `blocked -> todo|in_progress|failed|canceled`
- `done|failed|canceled` are terminal; self-loop updates are replay-only idempotent events

## Locking Rules

Active locks are stored in `task_locks`.
Conflicts are DB-enforced for both:
- exact same resource
- path-prefix overlap (for example, `src` conflicts with `src/a.py`)

## Watchdog Rules

Each task assignment should carry:
- `timeout_seconds`
- `heartbeat_interval_seconds`
- `last_heartbeat_at`

If a task remains `in_progress` and `now - last_heartbeat_at > timeout_seconds`, orchestrator should:
1. transition task to `blocked` with `TASK_TIMEOUT`
2. release active locks
3. replan assignment or escalate

## Troubleshooting

### `LockConflict`

Meaning: lock acquisition violated exact or path-prefix overlap rules.

Actions:
1. List active locks for the resource prefix.
2. Release stale locks for completed/canceled tasks.
3. Retry lock assignment.

### `DependencyNotMet`

Meaning: attempted to transition to `in_progress` while at least one dependency is not `done`.

Actions:
1. Query dependency states.
2. Complete or fail dependency tasks.
3. Retry transition.

### `InvalidTransition`

Meaning: transition is not in allowed state graph.

Actions:
1. Fetch task state/version.
2. Use a legal transition path.

### `ConcurrencyConflict`

Meaning: optimistic version check failed (`expected_version` stale).

Actions:
1. Re-read task row.
2. Retry transition with latest `version` using backoff: 0ms, 100ms, 250ms, 500ms.
3. If still conflicting, block and replan conflicting tasks serially.

### `TaskTimeout`

Meaning: liveness watchdog found `in_progress` task heartbeat beyond timeout budget.

Actions:
1. Transition task to `blocked` with `TASK_TIMEOUT`.
2. Release active task locks.
3. Transition `blocked -> todo` only when refreshed context and lock scope are ready.
4. Re-dispatch with same task id or create replacement task if ownership changed.

## Validation SQL

All examples assume SQLite shell connected to the target DB.

### Show migration version

```sql
SELECT MAX(version) AS latest_version FROM schema_versions;
```

### Inspect tasks

```sql
SELECT task_id, status, owner, retry_count, version, updated_at
FROM tasks
ORDER BY updated_at DESC
LIMIT 50;
```

### Inspect active locks

```sql
SELECT id, task_id, resource, active, created_at
FROM task_locks
WHERE active = 1
ORDER BY resource;
```

### Inspect task dependencies + current dependency state

```sql
SELECT td.task_id,
       td.depends_on_task_id,
       t.status AS depends_on_status
FROM task_dependencies td
JOIN tasks t ON t.task_id = td.depends_on_task_id
ORDER BY td.task_id, td.depends_on_task_id;
```

### Inspect recent task events

```sql
SELECT task_id, event_type, actor, payload, created_at
FROM task_events
ORDER BY created_at DESC
LIMIT 100;
```

## Migration Verification Procedure

1. Back up the DB file.
2. Start the app once to trigger migrations.
3. Validate:
   - `schema_versions` latest includes the task migrations.
   - Task tables/triggers exist.
4. Run one smoke transition flow:
   - create task
   - `todo -> in_progress`
   - `in_progress -> blocked`
   - `blocked -> todo`
   - `todo -> in_progress`
   - `in_progress -> done`

## Type Stub Decision

`src/memory_access/orm_models.pyi` is intentionally kept.
Reason: Peewee field accessors are dynamic; the stub improves static checking and editor hints for `TaskStore` and callers.
