#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
"""PreToolUse:Write|Edit hook — blocks writes outside the project directory.

When an orchestrator session is active (.claude/orchestrator/ exists),
all writes must resolve within cwd. No lock-scope logic — just a
filesystem boundary check.
"""

import json
import sys
from pathlib import Path


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    cwd = hook_input.get("cwd")
    tool_input = hook_input.get("tool_input", {})
    file_path = tool_input.get("file_path")

    if not cwd or not file_path:
        sys.exit(0)

    # Only enforce when an orchestrator session is active
    if not (Path(cwd) / ".claude" / "orchestrator").exists():
        sys.exit(0)

    # Resolve to absolute and check it's within cwd
    resolved = Path(file_path).resolve()
    cwd_resolved = Path(cwd).resolve()

    try:
        resolved.relative_to(cwd_resolved)
    except ValueError:
        error_response = {
            "decision": "deny",
            "reason": (
                f"Write to '{file_path}' blocked — outside project directory. "
                f"All writes must be within {cwd_resolved}."
            ),
        }
        print(json.dumps(error_response), file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
