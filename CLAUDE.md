# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

**memory-access** — a semantic memory MCP server that stores intent-based knowledge for AI agents. Text is decomposed into atomic insights, classified into semantic frames, embedded as vectors, and stored in SQLite with a subject-indexed knowledge graph.

> **Naming:** The canonical name is `memory-access`. All old references to `sem-mem`, `semantic-memory`, `SemMem`, or `brainspace` are deprecated and should be updated to `memory-access` / `MemoryAccessApp`.

## Commands

```bash
# Install dependencies
uv sync --group dev

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_storage.py

# Run a single test
uv run pytest tests/test_storage.py::TestInsightStoreInit::test_initialize_creates_tables

# Run MCP server directly
uv run memory-access
```

## Architecture

**Data flow (store):** User text → `Normalizer` (Claude haiku via Anthropic or Bedrock) decomposes into atomic insights → classifies each into a `Frame` with extracted subjects → `EmbeddingEngine` (OpenAI text-embedding-3-small) or `BedrockEmbeddingEngine` (Titan Embed V2) generates vectors → `InsightStore` persists to SQLite with auto-created subject links and relations.

**Data flow (search):** Query → embed → cosine similarity search in `InsightStore`, or subject-based lookup, or graph traversal via shared-subject relations.

### Source layout (`src/memory_access/`)

- **`models.py`** — `Frame` enum (CAUSAL, CONSTRAINT, PATTERN, EQUIVALENCE, TAXONOMY, PROCEDURE), `Insight`, `GitContext`, `SearchResult`
- **`normalizer.py`** — LLM decomposition/classification via Anthropic API (or Bedrock). Uses `DECOMPOSE_PROMPT` and `CLASSIFY_PROMPT`
- **`embeddings.py`** — Embedding generation (OpenAI or Bedrock Titan), L2-normalized float32 vectors. `create_embedding_engine()` factory selects provider.
- **`storage.py`** — `InsightStore` class: SQLite persistence, migration system, subject indexing, knowledge graph queries
- **`server.py`** — `MemoryAccessApp` orchestrator + MCP tool definitions (insights, subject graph, knowledge bases, and task-state orchestration tools)

### Database

Default location: `~/.claude/memory-access/memory.db` (override with `MEMORY_DB_PATH` env var).

Four tables: `insights`, `subjects` (with `insight_subjects` junction), `insight_relations`, `subject_relations`. Schema versioned via `schema_versions` table.

### Migration system

Migrations are Python functions in `storage.py` (named `_migrate_NNN_*`), tracked in `schema_versions`, and run automatically on `InsightStore.initialize()`. They are idempotent. Currently at migration 004.

## Key Conventions

- All I/O is async (aiosqlite, async MCP handlers)
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — async test functions just work
- Tests use the `tmp_db` fixture from `conftest.py` for isolated database paths
- Subject kinds: `domain`, `entity`, `problem`, `resolution`, `context`, `repo`, `pr`, `person`, `project`, `task`
- Subject lists on insights (domains, entities, etc.) are stored as JSON-encoded arrays in TEXT columns
- Embeddings stored as raw float32 BLOBs

## Environment Variables

- `OPENAI_API_KEY` — required for embeddings (when using OpenAI provider)
- `ANTHROPIC_API_KEY` — required for normalization (when using Anthropic provider)
- `MEMORY_DB_PATH` — optional, overrides default DB location
- `EMBEDDING_PROVIDER` — `openai` (default) or `bedrock`
- `LLM_PROVIDER` — `anthropic` (default) or `bedrock`
- `AWS_PROFILE` — AWS SSO profile name (for Bedrock)
- `AWS_REGION` — AWS region (for Bedrock, default: `us-east-1`)
- `BEDROCK_EMBEDDING_MODEL` — Bedrock embedding model ID (default: `amazon.titan-embed-text-v2:0`)
- `BEDROCK_LLM_MODEL` — Bedrock Claude model ID (default: `us.anthropic.claude-haiku-4-5-20251001-v1:0`)

## Publishing

The git workflow automatically publishes to PyPI. To release a new version, just push a commit to the `main` branch of the memory-access repo. The GitHub Actions release workflow bumps versions in both `pyproject.toml` and `.claude-plugin/plugin.json` and publishes.

## Plugin

This repo is also a Claude Code plugin (`claude plugin install memory-access@emmahyde`). Plugin files live at the repo root: `.claude-plugin/`, `skills/`, `hooks/`, `agents/`.

### Plugin components

- **Skills:** `using-semantic-memory`, `multi-agent-operator-guide`
- **Agents:** `orchestrator` — coordinates parallel subagent dispatch with lock management
- **Hooks:** `PreCompact` (insight preservation), `UserPromptSubmit` (pending insights), `SubagentStop` (sync gate + async summary injection)

### Multi-agent orchestration (`skills/multi-agent-operator-guide/`)

- `references/subagent-directive.md` — behavioral contract injected into ANY agent's Task prompt (not a standalone agent type)
- `scripts/build_dispatch_prompt.py` — deterministic assembler: directive + assignment packet → complete Task prompt
- `scripts/validate_packet.py`, `scripts/validate_result.py` — schema validators for assignment/result packets (accept both JSON and YAML frontmatter)
- Orchestrator uses `tools:` whitelist in agent frontmatter to restrict capabilities (e.g. excludes TaskOutput)

### Design principles for agent workflows

- LLM prompts contain decision-making logic only — never mechanical steps (create files, touch markers, run scripts). Automate those with hooks, scripts, or programmatic wrappers.
- `TaskOutput` always returns full output into caller context — avoid it for token-sensitive orchestration. Use async command hooks with `additionalContext` instead.
- Hook type capabilities: `type: "agent"` and `type: "prompt"` can only return `{ok: true/false}`. Only async `type: "command"` hooks can inject `systemMessage`/`additionalContext`.
- Behavioral contracts that apply to any dispatched agent must be injectable directives, not standalone agent types (prevents dispatching other agent types).
