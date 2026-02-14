# Locking

Lock behavior for orchestrator assignment and validator checks.

## Resource Normalization

Normalize each `resource` before comparing:

1. trim whitespace
2. replace `\\` with `/`
3. collapse redundant separators using POSIX normalization
4. remove trailing `/` except root `/`
5. reject resources that normalize to empty strings

Examples:

- `src\\api\\handler.py` -> `src/api/handler.py`
- `src/api/` -> `src/api`

## Active Lock Model

A lock record contains:

- `task_id`
- `resource`
- `active` (`true|false`)

Only `active=true` locks participate in conflict checks.

## Conflict Semantics

Two locks conflict when either is true:

1. exact match:
   - `a == b`
2. path-prefix overlap:
   - `a` starts with `b + "/"`
   - or `b` starts with `a + "/"`

Examples:

- `src` conflicts with `src/api.py`
- `src/api` conflicts with `src/api/handler.py`
- `src/a.py` does not conflict with `src/b.py`

Decision table:

| A | B | Conflict |
|---|---|---|
| `src` | `src/api.py` | yes |
| `src/api` | `src/api` | yes |
| `src/api/` | `src/api/handler.py` | yes (after normalization) |
| `src/a.py` | `src/b.py` | no |
| `src` | `src2` | no |
| `./src` | `src/a.py` | yes (after normalization) |

## Assignment Rules

- Assignment packet `task.lock_scope` MUST be non-empty.
- `forbidden_scope` MUST NOT overlap `lock_scope`.
- Candidate `lock_scope` MUST NOT conflict with current active locks.

On violation return `LOCK_CONFLICT`.

## Release Rules

- Releasing locks sets `active=false`; do not delete lock history.
- Releasing all locks on terminal states is recommended.

## Determinism Requirements

- Conflict checks MUST use normalized paths.
- Results MUST be stable regardless of lock ordering in input.

## Limitation

Path-prefix locking does not detect semantic conflicts across disjoint paths.
Example: two tasks edit separate files that jointly define one API contract.
Use task dependencies or serial execution when semantic coupling exists.
