---
name: setup-memory-access
description: Interactive wizard to install and configure the memory-access MCP server and plugin
allowed-tools: ["Bash", "Read", "Edit", "Write", "AskUserQuestion"]
---

# Setup Sem-Mem

Walk the user through installing and configuring the memory-access semantic memory system. Execute each step sequentially, reporting progress as you go.

## Step 1: Check prerequisites

Run `which uv` to check if uv is installed.

If not installed, tell the user:

```
uv is required but not installed. Install it with:
  curl -LsSf https://astral.sh/uv/install.sh | sh
Then re-run /setup-memory-access.
```

Stop here if uv is missing.

## Step 2: Install MCP server

Run `uv tool list` and check if `memory-access` appears in the output.

- If already installed, report "memory-access is already installed" and continue.
- If not installed, run `uv tool install memory-access` and confirm it succeeds.

## Step 3: Install plugin

Read `~/.claude/settings.json` and check if `"memory-access@brainspace": true` appears in `enabledPlugins`.

- If already enabled, report "memory-access plugin is already enabled" and continue.
- If not enabled, run `claude plugin install memory-access@brainspace` and confirm it succeeds.

## Step 4: Choose providers

Use AskUserQuestion to ask both provider questions at once:

```json
{
  "questions": [
    {
      "question": "Which LLM provider should memory-access use for decomposing insights?",
      "header": "LLM provider",
      "multiSelect": false,
      "options": [
        {
          "label": "Anthropic (Recommended)",
          "description": "Uses Anthropic API directly. Requires ANTHROPIC_API_KEY."
        },
        {
          "label": "AWS Bedrock",
          "description": "Uses Claude via Bedrock. Requires AWS SSO profile."
        }
      ]
    },
    {
      "question": "Which embedding provider should memory-access use for vector search?",
      "header": "Embeddings",
      "multiSelect": false,
      "options": [
        {
          "label": "OpenAI (Recommended)",
          "description": "Uses text-embedding-3-small. Requires OPENAI_API_KEY."
        },
        {
          "label": "AWS Bedrock",
          "description": "Uses Titan Embed V2. Requires AWS SSO profile."
        }
      ]
    }
  ]
}
```

Store the user's choices for use in later steps.

## Step 5: Collect credentials

Based on the provider choices from Step 4, check which env vars are needed and whether they already exist.

### If Anthropic LLM was chosen:

Run `echo $ANTHROPIC_API_KEY` via Bash to check if it's set in the shell environment.

- If set (non-empty), report "ANTHROPIC_API_KEY detected in environment" and store the value.
- If not set, use AskUserQuestion:

```json
{
  "questions": [
    {
      "question": "ANTHROPIC_API_KEY is not set in your environment. How would you like to provide it?",
      "header": "Anthropic key",
      "multiSelect": false,
      "options": [
        {
          "label": "Enter API key now",
          "description": "You'll paste your key and it will be stored in the MCP server config."
        },
        {
          "label": "I'll set it in my shell profile",
          "description": "You'll add 'export ANTHROPIC_API_KEY=...' to ~/.zshrc yourself."
        }
      ]
    }
  ]
}
```

If they choose to enter it now, ask them to provide it (use AskUserQuestion with a text prompt). If they choose shell profile, note that the env block should reference `${ANTHROPIC_API_KEY}` instead of a literal value.

### If OpenAI embeddings were chosen:

Same flow as above but for `OPENAI_API_KEY`.

### If Bedrock was chosen (for either provider):

Run `aws sts get-caller-identity --profile default 2>&1` to check if AWS credentials work.

Use AskUserQuestion to collect:

```json
{
  "questions": [
    {
      "question": "What is your AWS SSO profile name?",
      "header": "AWS profile",
      "multiSelect": false,
      "options": [
        {
          "label": "default",
          "description": "Use the default AWS profile"
        },
        {
          "label": "Enter custom profile",
          "description": "Specify a named SSO profile"
        }
      ]
    },
    {
      "question": "Which AWS region should Bedrock use?",
      "header": "AWS region",
      "multiSelect": false,
      "options": [
        {
          "label": "us-east-1 (Recommended)",
          "description": "N. Virginia - broadest model availability"
        },
        {
          "label": "us-west-2",
          "description": "Oregon"
        },
        {
          "label": "eu-west-1",
          "description": "Ireland"
        }
      ]
    }
  ]
}
```

## Step 6: Database path

Use AskUserQuestion:

```json
{
  "questions": [
    {
      "question": "Where should memory-access store its database?",
      "header": "DB path",
      "multiSelect": false,
      "options": [
        {
          "label": "Default (~/.claude/memory-access/memory.db) (Recommended)",
          "description": "Standard location alongside other Claude Code data"
        },
        {
          "label": "Custom path",
          "description": "Specify a different location for the database file"
        }
      ]
    }
  ]
}
```

If custom, ask for the path.

## Step 7: Write configuration

Read `~/.claude/settings.json` with the Read tool.

Build the `mcpServers.memory-access` entry based on collected choices:

### For Anthropic + OpenAI:

```json
{
  "memory-access": {
    "command": "uvx",
    "args": ["memory-access"],
    "env": {
      "MEMORY_DB_PATH": "<db_path>",
      "ANTHROPIC_API_KEY": "<key_or_shell_ref>",
      "OPENAI_API_KEY": "<key_or_shell_ref>"
    }
  }
}
```

### For Bedrock (either or both providers):

```json
{
  "memory-access": {
    "command": "uvx",
    "args": ["memory-access"],
    "env": {
      "MEMORY_DB_PATH": "<db_path>",
      "EMBEDDING_PROVIDER": "bedrock",
      "LLM_PROVIDER": "bedrock",
      "AWS_PROFILE": "<profile>",
      "AWS_REGION": "<region>"
    }
  }
}
```

Only include `EMBEDDING_PROVIDER`/`LLM_PROVIDER` keys for providers actually set to Bedrock. A mixed config (e.g., Anthropic LLM + Bedrock embeddings) should only include the relevant keys for each.

### For Bedrock users, also set in global env:

Add `"CLAUDE_CODE_USE_BEDROCK": "1"` to the top-level `env` object in settings.json (not inside mcpServers).

### Merging rules:

- Use Read to get current settings.json content
- Parse the JSON mentally
- If `mcpServers` key exists, add `memory-access` to it without removing other servers
- If `mcpServers` key does not exist, create it
- Preserve all other existing keys (env, permissions, enabledPlugins, etc.)
- Use Edit tool for surgical updates, or Write tool if the merge is complex
- NEVER clobber existing configuration

## Step 8: Create database directory

Run `mkdir -p` on the parent directory of the chosen DB path (default: `~/.claude/memory-access/`).

## Step 9: Validate

Tell the user:

```
Configuration written to ~/.claude/settings.json

You must restart Claude Code to load the new MCP server:

  1. Exit Claude Code (type /exit or press Ctrl+C)
  2. Run `claude --continue`
  3. Try: `store_insight("Setup complete - memory-access is configured and working")`

The memory-access tools (store_insight, search_insights, etc.) will be available after restart.
```

## Summary output

After all steps complete, display a summary:

```
## memory-access Setup Complete

**MCP server**: installed via uv
**Plugin**: memory-access@brainspace enabled
**LLM provider**: <choice>
**Embedding provider**: <choice>
**Database**: <path>
**Config**: ~/.claude/settings.json

Restart Claude Code to activate. Run `/using-memory-access` for usage guide.
```

## Error handling

- If any install command fails, show the error output and suggest manual steps
- If settings.json can't be read or parsed, warn the user and offer to create a fresh config
- If API key validation fails, continue anyway but warn that the server may not start
- Never leave settings.json in a broken state — if a write fails, report what was attempted so the user can do it manually
