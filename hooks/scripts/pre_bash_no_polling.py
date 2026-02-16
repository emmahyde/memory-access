#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
"""PreToolUse:Bash hook — blocks polling and destructive commands during orchestrator sessions.

Blocked:
  - Polling: sleep
  - Destructive: rm (with -r/-f flags), git reset --hard, git clean, git checkout .
"""

import json
import re
import sys
from pathlib import Path


BLOCKED_PATTERNS = [
    # Polling
    (re.compile(r'\bsleep\b'), "sleep — end your turn and wait for the SubagentStop hook"),
    # Destructive
    (re.compile(r'\brm\s+.*-[^\s]*[rf]'), "rm with -r or -f flags"),
    (re.compile(r'\bgit\s+reset\s+--hard\b'), "git reset --hard"),
    (re.compile(r'\bgit\s+clean\b'), "git clean"),
    (re.compile(r'\bgit\s+checkout\s+\.'), "git checkout ."),
    (re.compile(r'\bgit\s+push\s+.*--force\b'), "git push --force"),
    (re.compile(r'\bgit\s+push\s+-f\b'), "git push -f"),
]


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    cwd = hook_input.get("cwd", "")
    tool_input = hook_input.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        sys.exit(0)

    if not (Path(cwd) / ".claude" / "orchestrator").exists():
        sys.exit(0)

    for pattern, label in BLOCKED_PATTERNS:
        if pattern.search(command):
            print(
                json.dumps({
                    "decision": "deny",
                    "reason": f"BLOCKED: {label}",
                }),
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
