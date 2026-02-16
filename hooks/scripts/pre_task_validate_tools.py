#!/usr/bin/env -S uv run --script
# /// script
# dependencies = []
# ///
"""PreToolUse hook for Task — validates that the chosen subagent_type
has the tools required by the subagent contract (Read, Write for
report/worklog output). Warns or blocks if required tools are missing."""

import json
import re
import sys
from pathlib import Path

REQUIRED_TOOLS = ["Read", "Write"]

BUILTIN_TOOL_SETS: dict[str, list[str] | None] = {
    "general-purpose": None,  # None = all tools
    "Bash": ["Bash"],
    "Explore": ["Glob", "Grep", "Read", "WebFetch", "WebSearch"],
    "Plan": ["Glob", "Grep", "Read", "WebFetch", "WebSearch"],
}


def find_agent_file(cwd: Path, agent_type: str) -> Path | None:
    search_dirs = [
        cwd / "agents",
        cwd / ".claude" / "agents",
        cwd / ".claude-plugin" / "agents",
    ]
    for search_dir in search_dirs:
        candidate = search_dir / f"{agent_type}.md"
        if candidate.is_file():
            return candidate
    return None


def parse_tools_from_frontmatter(agent_file: Path) -> list[str] | None:
    """Extract tools list from agent frontmatter. Returns None if no tools: line."""
    try:
        text = agent_file.read_text()
    except Exception:
        return None

    in_frontmatter = False
    for line in text.splitlines():
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            else:
                break
        if in_frontmatter and line.strip().startswith("tools:"):
            return re.findall(r'"(\w+)"', line)

    return None


def resolve_tool_set(cwd: Path, subagent_type: str) -> list[str] | None:
    """Resolve the tool set for a given subagent_type.
    Returns a list of tool names, or None meaning 'all tools available'."""
    agent_file = find_agent_file(cwd, subagent_type)
    if agent_file:
        tools = parse_tools_from_frontmatter(agent_file)
        # Agent file with no tools: line means all tools (no restriction)
        return tools

    # Check built-in types
    if subagent_type in BUILTIN_TOOL_SETS:
        return BUILTIN_TOOL_SETS[subagent_type]

    # Unknown type — assume it has all tools
    return None


def find_missing_tools(tool_set: list[str] | None) -> list[str]:
    """Check if required tools are present in the tool set.
    Returns list of missing tools. Empty list = all present."""
    if tool_set is None:
        return []
    return [t for t in REQUIRED_TOOLS if t not in tool_set]


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cwd_str = input_data.get("cwd")
    subagent_type = input_data.get("tool_input", {}).get("subagent_type")

    if not cwd_str or not subagent_type:
        sys.exit(0)

    cwd = Path(cwd_str)
    tool_set = resolve_tool_set(cwd, subagent_type)
    missing = find_missing_tools(tool_set)

    if not missing:
        sys.exit(0)

    detail = (
        f"subagent_type '{subagent_type}' is missing required tools: "
        f"{', '.join(missing)}. The subagent contract requires these for "
        f"writing task reports and worklogs."
    )
    orchestrated = (cwd / ".orchestrator").is_dir()

    if orchestrated:
        print(
            json.dumps({"decision": "deny", "reason": detail}),
            file=sys.stderr,
        )
        sys.exit(2)
    else:
        print(json.dumps({"systemMessage": f"Warning: {detail}"}))
        sys.exit(0)


if __name__ == "__main__":
    main()
