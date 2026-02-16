#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///

import sys
import json

from pathlib import Path
from time import time


def has_recent_task_report(outputs_dir: Path, seconds: int = 60) -> bool:
    """Check if any task report was modified within the last N seconds."""
    if not outputs_dir.exists():
        return False

    current_time = time()
    for report_file in outputs_dir.glob("task__*.md"):
        if current_time - report_file.stat().st_mtime <= seconds:
            return True
    return False


def is_orchestrated_subagent(cwd: Path) -> bool:
    """Check if this is an orchestrated subagent context."""
    outputs_dir = cwd / '.claude/orchestrator' / "outputs"
    active_dispatch = cwd / '.claude/orchestrator' / ".active_dispatch"

    return outputs_dir.exists() and active_dispatch.exists()


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    cwd_str = hook_input.get("cwd")
    if not cwd_str:
        sys.exit(0)

    cwd = Path(cwd_str)

    if not is_orchestrated_subagent(cwd):
        sys.exit(0)

    outputs_dir = cwd / '.claude/orchestrator' / "outputs"
    if not has_recent_task_report(outputs_dir, seconds=60):
        error_response = {
            "decision": "block",
            "reason": "Subagent must write task report to report_path before stopping. See [REQUIRED OUTPUT] in your contract."
        }
        print(json.dumps(error_response), file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
