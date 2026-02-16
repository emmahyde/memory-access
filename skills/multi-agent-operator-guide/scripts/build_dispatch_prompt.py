#!/usr/bin/env python3
"""Build a complete subagent dispatch prompt from an assignment packet JSON.

Usage:
    echo '{"schema_version":"1.0.0", ...}' | python build_dispatch_prompt.py

Reads assignment packet JSON from stdin, prepends the subagent directive,
and prints the complete prompt to stdout. The orchestrator pipes this into
the Task tool's `prompt` parameter.

Exit codes:
    0 — success, prompt printed to stdout
    1 — error, JSON error object printed to stdout
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DIRECTIVE_PATH = (
    Path(__file__).resolve().parent.parent
    / "references"
    / "subagent-directive.md"
)


def emit_error(code: str, reason: str) -> int:
    print(json.dumps({"allow": False, "code": code, "reason": reason}, separators=(",", ":")))
    return 1


def extract_directive(text: str) -> str:
    """Extract content between the --- line markers in the directive file."""
    lines = text.splitlines(keepends=True)
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if start is None:
                start = i + 1
            else:
                end = i
                break
    if start is None or end is None:
        return ""
    return "".join(lines[start:end]).strip()


def main() -> int:
    # Read assignment packet from stdin
    raw = sys.stdin.read().strip()
    if not raw:
        return emit_error("EMPTY_INPUT", "no assignment packet on stdin")

    try:
        packet = json.loads(raw)
    except json.JSONDecodeError as exc:
        return emit_error("SCHEMA_INVALID", f"invalid JSON: {exc}")

    if not isinstance(packet, dict):
        return emit_error("SCHEMA_INVALID", "assignment packet must be a JSON object")

    # Read directive
    if not DIRECTIVE_PATH.exists():
        return emit_error("MISSING_VALIDATOR", f"subagent directive not found at {DIRECTIVE_PATH}")

    directive = extract_directive(DIRECTIVE_PATH.read_text())
    if not directive:
        return emit_error("MISSING_VALIDATOR", "could not extract directive from subagent-directive.md")

    # Ensure report_path is set in the task object
    task = packet.get("task", {})
    if isinstance(task, dict) and "report_path" not in task:
        task_id = task.get("task_id", "unknown")
        title = task.get("title", task_id)
        # Convert title to snake_case descriptor
        descriptor = "_".join(title.lower().split())
        descriptor = re.sub(r"[^a-z0-9_]", "", descriptor)
        task["report_path"] = f".claude/orchestrator/outputs/task__{descriptor}.md"
        packet["task"] = task

    # Build prompt
    prompt = f"""{directive}

[ASSIGNMENT PACKET]
{json.dumps(packet, indent=2)}"""

    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
