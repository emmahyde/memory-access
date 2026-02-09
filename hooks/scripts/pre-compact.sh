#!/bin/bash
# PreCompact hook: Preserve knowledge before context compaction.
#
# Strategy:
# 1. Create a marker file so a post-compaction hook knows insights are pending
# 2. Instruct the LLM to include insights in a structured <pending-insights>
#    block within the compaction summary — these survive compaction and get
#    stored automatically on the next user message.

set -euo pipefail

# Read hook input from stdin
input=$(cat)

# Create marker file so post-compaction UserPromptSubmit hook can detect pending insights
MARKER_DIR="$HOME/.claude/memory-access"
MARKER_FILE="$MARKER_DIR/insights-pending"
mkdir -p "$MARKER_DIR"
touch "$MARKER_FILE"

# System message instructs the LLM to embed insights in a structured block
# within the compaction summary. The post-compaction hook will trigger storage.
cat <<'GUIDANCE'
{
  "systemMessage": "IMPORTANT — Pre-compaction knowledge preservation.\n\nYou MUST include a <pending-insights> block in your compaction summary containing insights worth preserving. Format each insight as a line with text and domain:\n\n<pending-insights>\n- text: \"Description of the insight\" | domain: \"comma,separated,tags\"\n- text: \"Another insight\" | domain: \"relevant,domains\"\n</pending-insights>\n\nWhat to include:\n1. Non-obvious technical decisions and WHY they were made\n2. Bug root causes and their fixes (problem-resolution pairs)\n3. Architectural patterns discovered or established\n4. Solutions that took multiple attempts to find\n5. Key codebase facts that were expensive to discover\n6. Structural relationships (repo contains project, person works_on project)\n\nInclude git context (repo, pr, author, project) as additional fields if applicable:\n- text: \"...\" | domain: \"...\" | repo: \"org/repo\" | project: \"project-name\"\n\nThis block will be automatically processed after compaction to store insights in semantic memory. Do NOT skip this block — it is the ONLY way insights survive compaction."
}
GUIDANCE
