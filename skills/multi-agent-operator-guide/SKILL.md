---
name: multi-agent-operator-guide
description: Operate strict orchestrator/subagent workflows with enforceable contracts, lock management, and fresh-context handoff execution. Use when planning or running agent swarms, validating assignment/result packets, preventing lock overlap, reconciling task ledgers, or recovering blocked multi-agent runs.
---

# Multi-Agent Operator Guide

Run strict multi-agent execution with machine validation, not prompt text alone.

## When To Use

Use this skill when you need deterministic orchestration across multiple agents, especially when tasks run in parallel and require lock-safe writes, append-only worklogs, and schema-validated handoffs.

## Mandatory Execution Loop

1. Spawn orchestrator agent (`memory-access:orchestrator`) with global objective and constraints
2. Validate assignment packet (`scripts/validate_packet.py`)
3. Check lock overlap (`scripts/check_lock_overlap.py`)
4. Build dispatch prompt via `scripts/build_dispatch_prompt.py` and spawn any agent type via Task tool
5. Validate result packet (`scripts/validate_result.py`)
6. Reconcile ledger/locks/events (`scripts/reconcile_ledger.py`)

If validator scripts are unavailable, stop and mark run `blocked` with `MISSING_VALIDATOR`.

## Critical Schemas (Inline)

These two payloads are the minimum required control-plane artifacts for a first valid run.

### Assignment Packet (orchestrator -> subagent)

```json
{
  "schema_version": "1.0.0",
  "run_id": "3f56dc4d-35cf-4f97-925c-0b04a6fe8bf4",
  "packet_type": "assignment",
  "global_objective": "Implement endpoint tests",
  "task": {
    "task_id": "T-12",
    "title": "Add endpoint tests",
    "type": "parallelizable",
    "dependencies": [],
    "lock_scope": ["tests/test_api.py"],
    "forbidden_scope": ["src/"],
    "acceptance_criteria": ["All endpoint tests pass"],
    "worklog_path": "worklogs/T-12.jsonl",
    "timeout_seconds": 1200,
    "heartbeat_interval_seconds": 120,
    "priority": "high"
  },
  "active_locks": [
    {"task_id": "T-9", "resource": "src/api.py", "active": true}
  ],
  "context_package": [
    {"kind": "file", "value": "tests/test_api.py"},
    {"kind": "constraint", "value": "Do not edit src/api.py"}
  ],
  "required_output_schema": "subagent_result_v1"
}
```

### Result Packet (subagent -> orchestrator)

```json
{
  "schema_version": "1.0.0",
  "run_id": "3f56dc4d-35cf-4f97-925c-0b04a6fe8bf4",
  "task_id": "T-12",
  "status": "done",
  "changes": [
    {"resource": "tests/test_api.py", "action": "edit", "evidence": "Added endpoint assertions"}
  ],
  "acceptance_check": [
    {"criterion": "All endpoint tests pass", "status": "pass", "evidence": "pytest tests/test_api.py"}
  ],
  "worklog_path": "worklogs/T-12.jsonl",
  "notes_for_orchestrator": ["No conflicts, ready for merge"]
}
```

## Read Order

1. `references/contracts.md` (source of truth)
2. `references/error-codes.md`
3. `references/state-machine.md`
4. `references/locking.md`

The orchestrator role is a proper agent (`agents/orchestrator.md`) — its contract is the system prompt when spawned. The subagent contract (`references/subagent-directive.md`) is a directive preamble that the orchestrator injects into the prompt of any agent it dispatches, ensuring lock/scope/result compliance regardless of agent type.

Read only additional references as needed:

- `references/fresh-context.md` for new-session handoff/reset protocol
- `references/security.md` for untrusted context handling
- `references/slo.md` for quality targets and operational metrics

## Implementation Steps

1. Start from `assets/handoff-template.json` and fill run metadata.
2. Build assignment packet and run `scripts/validate_packet.py`.
3. Run `scripts/check_lock_overlap.py` before dispatch.
4. Dispatch agent via Task tool with subagent directive + assignment packet; agent appends worklog entries.
5. Validate result packet with `scripts/validate_result.py`.
6. Reconcile with `scripts/reconcile_ledger.py` before marking done.
7. Use `examples/README.md` for a complete runnable walkthrough with expected validator outputs.

## Conductor-Inspired Workflow

Borrowed from `wshobson/agents` conductor patterns:

- Keep task context explicit and minimal per assignment packet.
- Treat artifacts as first-class: objective/spec, plan, ledger, worklog.
- Use visible status progression (`todo`, `in_progress`, `blocked`, terminal) and do not skip validation gates.
- Prefer deterministic handoff artifacts over chat-history continuity.

## Output and Error Discipline

- Use `schema_version: 1.0.0` on all machine payloads.
- Use only error codes defined in `references/error-codes.md`.
- Never mark a task `done` without acceptance evidence.
- Never allow exact or path-prefix lock overlap.
- Never merge `notes_for_orchestrator` without secret-pattern filtering.

## Do Not

- Do not combine orchestrator and execution roles in one agent.
- Do not pass full repository context to every subagent.
- Do not bypass validators for speed.
