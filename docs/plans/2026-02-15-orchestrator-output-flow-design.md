# Orchestrator Output Flow Design

## Problem

When the orchestrator dispatches background subagents via the Task tool, `TaskOutput` returns the subagent's full return message into the orchestrator's context. For multi-agent runs with several parallel workers, this consumes significant tokens. The orchestrator needs to know task status without ingesting verbose output.

## Solution: Three-Stage Output Flow

### Stage 1: Subagent writes task report before returning

The subagent directive requires the subagent to, as its final actions:

1. Write a task report to the path provided in the assignment packet (`report_path` field), e.g. `{CLAUDE_PROJECT_DIR}/.orchestrator/outputs/task__{snake_case_descriptor}.md`
2. Return a short message to the parent: `"Task {status}. Report: {report_path}"`

The report uses markdown with YAML frontmatter:

```markdown
---
schema_version: "1.0.0"
run_id: "3f56dc4d-35cf-4f97-925c-0b04a6fe8bf4"
task_id: "T-12"
status: done
files_touched:
  - resource: "tests/test_auth.py"
    action: edit
  - resource: "tests/fixtures/auth.json"
    action: create
acceptance_check:
  - criterion: "All endpoint tests pass"
    status: pass
    evidence: "pytest tests/test_auth.py — 12 passed"
notes_for_orchestrator:
  - "No conflicts, ready for merge"
worklog_path: "worklogs/T-12.jsonl"
---

## Summary

Added endpoint tests for the auth module covering login, logout, and token refresh flows.

## Decisions

- Used pytest fixtures instead of unittest setUp to match existing test patterns.

## Issues

None.
```

### Stage 2: Async command hook on SubagentStop

An async command hook (`type: "command"`, `async: true`) fires for every SubagentStop.

Script: `hooks/scripts/subagent-stop-summary.sh`

Behavior:
1. Reads hook input JSON from stdin.
2. Scans for `.orchestrator/outputs/` files matching recent modification time. If none found, this is not an orchestrated subagent — `exit 0` silently.
3. Reads YAML frontmatter from the task report file.
4. Emits JSON with both output channels:

```json
{
  "systemMessage": "Output for task__add_endpoint_tests has been injected into context.",
  "additionalContext": "<subagent-result task_id=\"T-12\" status=\"done\" report_path=\".orchestrator/outputs/task__add_endpoint_tests.md\">\n  <files_touched>\n    <file resource=\"tests/test_auth.py\" action=\"edit\" />\n    <file resource=\"tests/fixtures/auth.json\" action=\"create\" />\n  </files_touched>\n  <acceptance_check>\n    <criterion name=\"All endpoint tests pass\" status=\"pass\" evidence=\"pytest tests/test_auth.py — 12 passed\" />\n  </acceptance_check>\n  <notes>\n    <note>No conflicts, ready for merge</note>\n  </notes>\n</subagent-result>"
}
```

- `systemMessage` — user sees "Output for task__add_endpoint_tests has been injected into context."
- `additionalContext` — XML-tagged summary delivered to Claude/orchestrator on the next conversation turn

Because the hook is async, it does not block the subagent from stopping. The summary arrives on the orchestrator's next turn.

### Stage 3: Orchestrator attends to injected context

The orchestrator receives the `<subagent-result>` XML in its context. For the common case (all acceptance criteria pass, no actionable notes), it updates the ledger and proceeds. If it needs more detail (failures, blocks, ambiguous notes), it reads the full task report at `report_path`.

## Changes Required

### 1. Subagent directive (`references/subagent-directive.md`)

Replace `[REQUIRED OUTPUT]` section:

**Before:** Return JSON result envelope as final output.

**After:**
- Write task report to `report_path` (from assignment packet) as markdown with YAML frontmatter.
- Frontmatter fields: schema_version, run_id, task_id, status, files_touched, acceptance_check, notes_for_orchestrator, worklog_path.
- Markdown body: summary of work, decisions made, issues encountered.
- Return one line: `"Task {status}. Report: {report_path}"`

### 2. hooks.json

Add async command hook for SubagentStop:

```json
{
  "SubagentStop": [
    {
      "matcher": ".*",
      "hooks": [
        {
          "type": "command",
          "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/subagent-stop-summary.sh",
          "async": true,
          "timeout": 15
        }
      ]
    }
  ]
}
```

### 3. New script: `hooks/scripts/subagent-stop-summary.sh`

Bash script that:
- Reads hook input from stdin
- Finds the most recently modified `.orchestrator/outputs/task__*.md` file
- Parses YAML frontmatter (using simple text extraction, no YAML library needed)
- Formats XML-tagged `additionalContext`
- Emits JSON with `systemMessage` + `additionalContext`

### 4. `build_dispatch_prompt.py`

Add `report_path` to the assignment packet. The orchestrator provides this when building assignments:

```json
{
  "task": {
    "report_path": ".orchestrator/outputs/task__{snake_case_descriptor}.md",
    ...
  }
}
```

### 5. Orchestrator control loop (`agents/orchestrator.md`)

Update to:
- Include `report_path` in every assignment packet
- After dispatching background workers, do NOT call `TaskOutput` — it returns full output into context, defeating the token optimization
- Instead, wait for `<subagent-result>` XML to appear in context via the async hook's `additionalContext`
- Read full report only when investigation is needed
- Run `validate_result.py` on the report frontmatter before ledger transitions

### 6. `validate_result.py`

Adapt to accept YAML frontmatter input (parsed to JSON) in addition to raw JSON. Or add a wrapper script that extracts frontmatter and pipes to existing validator.

## Properties

| Property | Mechanism |
|---|---|
| User visibility | `systemMessage` one-liner |
| Claude context injection | `additionalContext` with XML tags, next turn |
| Token cost | ~10-20 lines XML summary, not full output |
| Non-orchestrated subagents | Hook finds no report file, exits silently |
| Durability | Task report on disk, survives compaction |
| No LLM in hook | Pure bash, deterministic, fast |
| Non-blocking | Async hook, subagent stops immediately |
