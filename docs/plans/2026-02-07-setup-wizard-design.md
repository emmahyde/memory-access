# Setup Wizard Design

## Overview

A Claude Code slash command (`/setup-memory-access`) that interactively configures the memory-access MCP server and plugin. Walks users through provider selection, credential setup, and writes config to `~/.claude/settings.json`.

## Wizard Flow

1. **Check prerequisites** - Is `uv` installed?
2. **Install MCP server** - `uv tool install memory-access` (skip if already installed)
3. **Install plugin** - `claude plugin install memory-access@emmahyde` (skip if already enabled)
4. **Choose LLM provider** - Anthropic (default) or Bedrock
5. **Choose embedding provider** - OpenAI (default) or Bedrock
6. **Collect credentials** - Based on provider choices, check if required env vars exist in shell. If missing, prompt user to provide them.
7. **DB path** - Use default `~/.claude/memory-access/memory.db` or enter custom path
8. **Write MCP config** - Generate `mcpServers` entry and merge into `~/.claude/settings.json`
9. **Validate** - Confirm server starts with a test invocation

## Config Output

### Anthropic + OpenAI (default)

Adds to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "memory-access": {
      "command": "uvx",
      "args": ["memory-access"],
      "env": {
        "MEMORY_DB_PATH": "~/.claude/memory-access/memory.db",
        "ANTHROPIC_API_KEY": "<user-provided>",
        "OPENAI_API_KEY": "<user-provided>"
      }
    }
  }
}
```

### Bedrock

Adds to `~/.claude/settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_USE_BEDROCK": "1"
  },
  "mcpServers": {
    "memory-access": {
      "command": "uvx",
      "args": ["memory-access"],
      "env": {
        "MEMORY_DB_PATH": "~/.claude/memory-access/memory.db",
        "EMBEDDING_PROVIDER": "bedrock",
        "LLM_PROVIDER": "bedrock",
        "AWS_PROFILE": "<user-provided>",
        "AWS_REGION": "<user-provided>"
      }
    }
  }
}
```

## Implementation

### File

`commands/setup-memory-access.md` - Prompt-based slash command with YAML frontmatter.

### Approach

The command is a structured prompt that instructs Claude to execute the wizard steps sequentially using:
- `AskUserQuestion` for multi-choice selections (providers, DB path)
- `Bash` for install commands (`uv tool install`, `claude plugin install`) and prerequisite checks (`which uv`)
- `Read` to load current `~/.claude/settings.json`
- `Edit` to merge new config into `~/.claude/settings.json`

### Key Decisions

- **`uvx memory-access`** as MCP command (no `cwd` needed, cleaner than `python3 -m`)
- **API keys in MCP server `env` block**, not global - keeps credentials scoped to memory-access
- **`CLAUDE_CODE_USE_BEDROCK`** in global `env` block when Bedrock is selected
- **Merges into existing settings.json** without clobbering other config
- **Validates at end** by confirming the server process can start
