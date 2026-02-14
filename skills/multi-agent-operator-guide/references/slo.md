# SLOs

Operational targets for multi-agent runs.

## Core SLOs

- Packet validation pass rate: `>= 99%`
- Lock conflict rate per dispatch round: `<= 5%`
- First-pass subagent completion rate: `>= 85%`
- Retry success rate (single retry budget): `>= 60%`
- Mean task completion latency (parallelizable tasks): team-defined baseline + trend down

## Error Budget

Track by code family:

- contract errors (`SCHEMA_INVALID`, `MISSING_REQUIRED_INPUT`)
- lock/scope errors (`LOCK_CONFLICT`, `SCOPE_VIOLATION`)
- dependency/state errors (`DEPENDENCY_NOT_MET`, `INVALID_TRANSITION`)
- compliance errors (`NON_COMPLIANT`)

## Minimum Metrics Per Run

- total tasks
- completed/blocked/failed/canceled counts
- number of lock conflicts
- number of validation denies by code
- retries attempted and retries succeeded

## Reporting Cadence

- per run summary at close
- weekly trend rollup for recurring failure patterns
