# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A semantic memory MCP server that stores intent-based knowledge for AI agents. Text is decomposed into atomic insights, classified into semantic frames, embedded as vectors, and stored in SQLite with a subject-indexed knowledge graph.

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run all tests
python3 -m pytest

# Run a single test file
python3 -m pytest tests/test_storage.py

# Run a single test
python3 -m pytest tests/test_storage.py::TestInsightStoreInit::test_initialize_creates_tables

# Run MCP server directly
python3 -m semantic_memory.server
```

## Architecture

**Data flow (store):** User text → `Normalizer` (Claude haiku) decomposes into atomic insights → classifies each into a `Frame` with extracted subjects → `EmbeddingEngine` (OpenAI text-embedding-3-small) generates vectors → `InsightStore` persists to SQLite with auto-created subject links and relations.

**Data flow (search):** Query → embed → cosine similarity search in `InsightStore`, or subject-based lookup, or graph traversal via shared-subject relations.

### Source layout (`src/semantic_memory/`)

- **`models.py`** — `Frame` enum (CAUSAL, CONSTRAINT, PATTERN, EQUIVALENCE, TAXONOMY, PROCEDURE), `Insight`, `GitContext`, `SearchResult`
- **`normalizer.py`** — LLM decomposition/classification via Anthropic API. Uses `DECOMPOSE_PROMPT` and `CLASSIFY_PROMPT`
- **`embeddings.py`** — OpenAI embedding generation, L2-normalized float32 vectors
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

- `OPENAI_API_KEY` — required for embeddings
- `ANTHROPIC_API_KEY` — required for normalization (Claude)
- `MEMORY_DB_PATH` — optional, overrides default DB location
