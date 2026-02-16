#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///

import sys
import json
from pathlib import Path


SYSTEM_MESSAGE = """IMPORTANT — Pre-compaction knowledge preservation.

You MUST include a <pending-insights> block in your compaction summary containing insights worth preserving. Format each insight as a line with text and domain:

<pending-insights>
- text: "Description of the insight" | domain: "comma,separated,tags"
- text: "Another insight" | domain: "relevant,domains"
</pending-insights>

What to include:
1. Non-obvious technical decisions and WHY they were made
2. Bug root causes and their fixes (problem-resolution pairs)
3. Architectural patterns discovered or established
4. Solutions that took multiple attempts to find
5. Key codebase facts that were expensive to discover
6. Structural relationships (repo contains project, person works_on project)

Include git context (repo, pr, author, project) as additional fields if applicable:
- text: "..." | domain: "..." | repo: "org/repo" | project: "project-name"

This block will be automatically processed after compaction to store insights in semantic memory. Do NOT skip this block — it is the ONLY way insights survive compaction."""


def main():
    # Consume stdin (not used but required)
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        pass

    # Create marker directory and file
    marker_dir = Path.home() / ".claude" / "memory-access"
    marker_dir.mkdir(parents=True, exist_ok=True)

    marker_file = marker_dir / "insights-pending"
    marker_file.touch()

    response = {"systemMessage": SYSTEM_MESSAGE}
    print(json.dumps(response))
    sys.exit(0)


if __name__ == "__main__":
    main()
