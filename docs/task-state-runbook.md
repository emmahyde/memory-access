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
- `blocked -> in_progress|failed|canceled`
- `done|failed|canceled` are terminal

## Locking Rules

Active locks are stored in `task_locks`.
Conflicts are DB-enforced for both:
- exact same resource
- path-prefix overlap (for example, `src` conflicts with `src/a.py`)

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
2. Retry transition with latest `version`.

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
   - `in_progress -> done`

## Type Stub Decision

`src/memory_access/orm_models.pyi` is intentionally kept.
Reason: Peewee field accessors are dynamic; the stub improves static checking and editor hints for `TaskStore` and callers.
