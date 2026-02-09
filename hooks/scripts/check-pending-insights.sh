#!/bin/bash
# UserPromptSubmit hook: Check for pending insights from a pre-compaction cycle.
#
# If the marker file exists, a compaction recently occurred and the compaction
# summary should contain a <pending-insights> block. Emit a system message
# telling the agent to extract and store them, then clean up the marker.

set -euo pipefail

MARKER_FILE="$HOME/.claude/memory-access/insights-pending"

if [ ! -f "$MARKER_FILE" ]; then
  # No pending insights — no-op
  echo '{"continue": true}'
  exit 0
fi

# Remove marker immediately to prevent re-triggering on subsequent messages
rm -f "$MARKER_FILE"

cat <<'INSTRUCTION'
{
  "continue": true,
  "systemMessage": "POST-COMPACTION INSIGHT STORAGE: A compaction just occurred and your context summary should contain a <pending-insights> block with insights to preserve.\n\nYour task: spawn a BACKGROUND agent to store these insights. Do this silently without disrupting the user's request.\n\n1. Parse the <pending-insights> block from your current context\n2. For each insight, call `store_insight` with the text, domain, and any git context fields\n3. For any structural relationships mentioned, call `add_subject_relation`\n4. If no <pending-insights> block is found in your context, skip silently\n\nUse: Task(subagent_type=\"general-purpose\", model=\"haiku\", run_in_background=true, prompt=\"...\")\n\nIMPORTANT: Do not let this interfere with the user's actual request. Handle it as a background task and proceed with whatever the user asked."
}
INSTRUCTION
