# Orchestrator Hook Enforcement Spec

This document defines enforceable hook points for a strict two-role multi-agent runtime.

## Enforcement Model

Each hook is a command that receives JSON on `stdin` and returns JSON to `stdout`.

- Exit code `0`: allow progression.
- Exit code non-zero: deny progression.
- Deny payload format:

```json
{
  "allow": false,
  "code": "RULE_ID",
  "reason": "One-line failure reason",
  "details": {}
}
```

- Allow payload format:

```json
{
  "allow": true,
  "code": "OK",
  "reason": "Validation passed"
}
```

## Hook Points

| Hook | Purpose | Must Enforce |
|---|---|---|
| `PreDispatch` | Validate orchestrator assignment packet | Required fields, lock scope present, no active overlap, forbidden scope present, worklog path present |
| `PreExecution` | Validate subagent startup context | Dependencies complete, lock still valid, sandbox scope ready |
| `PreWrite` | Guard each write/tool mutation | Mutations only within lock scope, no forbidden paths |
| `PostExecution` | Validate subagent output | Output schema valid, changed files align with lock scope, worklog appended |
| `PreComplete` | Gate task completion | All acceptance checks pass with evidence |
| `OnLockUpdate` | Global conflict detector | No overlapping active locks |
| `PreCompact` | Preserve state before compaction | Snapshot ledger, locks, blockers, and learnings |

## Canonical Payload Contracts

### `PreDispatch`

```json
{
  "task_id": "T-123",
  "assignment": {
    "lock_scope": ["src/a.py", "tests/test_a.py"],
    "forbidden_scope": ["src/b.py"],
    "acceptance_criteria": ["tests pass"],
    "worklog_path": "worklogs/T-123.md"
  },
  "active_locks": [
    {"task_id": "T-101", "owner": "agent-2", "status": "in_progress", "lock_scope": ["src/c.py"]}
  ]
}
```

### `PostExecution`

```json
{
  "task_id": "T-123",
  "result": {
    "status": "done",
    "changes": ["src/a.py"],
    "acceptance_check": [{"criterion": "tests pass", "status": "pass", "evidence": "pytest -q"}],
    "worklog_path": "worklogs/T-123.md"
  },
  "assignment": {
    "lock_scope": ["src/a.py", "tests/test_a.py"],
    "forbidden_scope": ["src/b.py"]
  },
  "changed_files": ["src/a.py"]
}
```

### `PreComplete`

```json
{
  "task_id": "T-123",
  "acceptance_check": [
    {"criterion": "tests pass", "status": "pass", "evidence": "pytest tests/test_a.py"}
  ],
  "required_criteria": ["tests pass"]
}
```

## Rule IDs

- `R-PD-001`: missing required dispatch field
- `R-PD-002`: empty lock scope
- `R-PD-003`: lock overlap with active task
- `R-PD-004`: missing forbidden scope
- `R-PD-005`: missing worklog path
- `R-PE-001`: dependency not complete
- `R-PW-001`: write outside lock scope
- `R-PW-002`: write inside forbidden scope
- `R-PO-001`: invalid result schema
- `R-PO-002`: changed file outside lock scope
- `R-PO-003`: missing worklog file
- `R-PC-001`: criterion missing
- `R-PC-002`: criterion not passed
- `R-PC-003`: missing evidence
- `R-LK-001`: overlapping active locks

## Pass/Fail Behavior

- Any deny result MUST block progression for that task.
- Denied tasks MUST transition to `blocked` or `failed` with `code` and `reason` recorded.
- A blocked task MAY be retried exactly once after orchestrator updates assignment context.
- Repeated failure SHOULD escalate model or replan serially.
