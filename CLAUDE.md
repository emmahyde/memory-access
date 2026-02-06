# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A semantic memory MCP server that stores intent-based knowledge for AI agents. Text is decomposed into atomic insights, classified into semantic frames, embedded as vectors, and stored in SQLite with a subject-indexed knowledge graph.

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
uv run semantic-memory
```

## Architecture

**Data flow (store):** User text → `Normalizer` (Claude haiku via Anthropic or Bedrock) decomposes into atomic insights → classifies each into a `Frame` with extracted subjects → `EmbeddingEngine` (OpenAI text-embedding-3-small) or `BedrockEmbeddingEngine` (Titan Embed V2) generates vectors → `InsightStore` persists to SQLite with auto-created subject links and relations.

**Data flow (search):** Query → embed → cosine similarity search in `InsightStore`, or subject-based lookup, or graph traversal via shared-subject relations.

### Source layout (`src/semantic_memory/`)

- **`models.py`** — `Frame` enum (CAUSAL, CONSTRAINT, PATTERN, EQUIVALENCE, TAXONOMY, PROCEDURE), `Insight`, `GitContext`, `SearchResult`
- **`normalizer.py`** — LLM decomposition/classification via Anthropic API (or Bedrock). Uses `DECOMPOSE_PROMPT` and `CLASSIFY_PROMPT`
- **`embeddings.py`** — Embedding generation (OpenAI or Bedrock Titan), L2-normalized float32 vectors. `create_embedding_engine()` factory selects provider.
- **`storage.py`** — `InsightStore` class: SQLite persistence, migration system, subject indexing, knowledge graph queries
- **`server.py`** — `SemanticMemoryApp` orchestrator + MCP tool definitions (9 tools: `store_insight`, `search_insights`, `list_insights`, `update_insight`, `forget`, `search_by_subject`, `related_insights`, `add_subject_relation`, `get_subject_relations`)

### Database

Default location: `~/.claude/semantic-memory/memory.db` (override with `MEMORY_DB_PATH` env var).

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

## Plugin

This repo is also a Claude Code plugin (`claude plugin install semantic-memory@brainspace`). Plugin files live at the repo root: `.claude-plugin/`, `skills/`, `hooks/`. Includes a `using-semantic-memory` skill and a `PreCompact` hook.
