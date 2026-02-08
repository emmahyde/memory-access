#!/bin/bash
# PreCompact hook: Extract and store insights from the current conversation
# before context compaction occurs. This preserves knowledge that would
# otherwise be lost when the conversation window is compacted.
#
# Strategy: Read hook input, output a system message instructing Claude
# to store key insights via memory-access MCP tools before compaction.

set -euo pipefail

# Read hook input from stdin
input=$(cat)

# Extract transcript path from hook input
transcript_path=$(echo "$input" | jq -r '.transcript_path // empty')

if [ -z "$transcript_path" ] || [ ! -f "$transcript_path" ]; then
  # No transcript available — provide guidance without transcript content
  cat <<'GUIDANCE'
{
  "systemMessage": "IMPORTANT — Pre-compaction knowledge preservation: Before this context is compacted, review the conversation for key insights, decisions, discoveries, and solutions. For each significant finding, call the `store_insight` MCP tool with appropriate domain tags and git context (repo, pr, author, project, task) if applicable. Focus on:\n1. Non-obvious technical decisions and their rationale\n2. Bug fixes and their root causes\n3. Architectural patterns discovered or established\n4. Solutions to problems that took multiple attempts\n5. Key facts about the codebase that were expensive to discover\n\nStore these BEFORE compaction occurs so they persist in semantic memory."
}
GUIDANCE
  exit 0
fi

# Transcript exists — include a summary directive
cat <<'GUIDANCE'
{
  "systemMessage": "IMPORTANT — Pre-compaction knowledge preservation: Before this context is compacted, review the conversation for key insights, decisions, discoveries, and solutions that should be preserved in semantic memory. For each significant finding, call the `store_insight` MCP tool with:\n- Descriptive text capturing the insight\n- Relevant domain tags (e.g., 'python,asyncio' or 'react,hooks')\n- Git context if applicable (repo, pr, author, project, task)\n- Source indicating this session\n\nPrioritize storing:\n1. Non-obvious technical decisions and WHY they were made\n2. Bug root causes and their fixes\n3. Architectural patterns discovered or established\n4. Solutions that took multiple attempts to find\n5. Key codebase facts that were expensive to discover\n6. Problem-resolution pairs (what broke and how it was fixed)\n\nAlso call `add_subject_relation` for any structural relationships discovered (e.g., repo contains project, person works_on project).\n\nDo this NOW before compaction loses this context."
}
GUIDANCE
