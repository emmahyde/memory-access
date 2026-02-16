#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///

import sys
import json
from pathlib import Path


SYSTEM_MESSAGE = """POST-COMPACTION INSIGHT STORAGE: A compaction just occurred and your context summary should contain a <pending-insights> block with insights to preserve.

Your task: spawn a BACKGROUND agent to store these insights. Do this silently without disrupting the user's request.

1. Parse the <pending-insights> block from your current context
2. For each insight, call `store_insight` with the text, domain, and any git context fields
3. For any structural relationships mentioned, call `add_subject_relation`
4. If no <pending-insights> block is found in your context, skip silently

Use: Task(subagent_type=\"general-purpose\", model=\"haiku\", run_in_background=true, prompt=\"...\")

IMPORTANT: Do not let this interfere with the user's actual request. Handle it as a background task and proceed with whatever the user asked."""


def main():
    marker_file = Path.home() / ".claude" / "memory-access" / "insights-pending"

    if not marker_file.exists():
        response = {"continue": True}
        print(json.dumps(response))
        sys.exit(0)

    # Delete the marker file
    marker_file.unlink()

    response = {
        "continue": True,
        "systemMessage": SYSTEM_MESSAGE
    }
    print(json.dumps(response))
    sys.exit(0)


if __name__ == "__main__":
    main()
