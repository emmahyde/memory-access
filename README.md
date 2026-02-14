# memory-access

An MCP server that gives AI agents persistent, intent-based memory. Text is decomposed into atomic insights, classified into semantic frames, embedded as vectors, and stored in a SQLite knowledge graph with subject indexing.

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/emmahyde/memory-access.git
cd memory-access
uv sync --group dev
```

Or install from PyPI:

```bash
pip install memory-access
# or
uv add memory-access
```

Requires Python 3.12+.

### 2. Set environment variables

For OpenAI + Anthropic (default):

```bash
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

For AWS Bedrock:

```bash
export EMBEDDING_PROVIDER=bedrock
export LLM_PROVIDER=bedrock
export AWS_PROFILE=your-sso-profile
export AWS_REGION=us-east-1
```

### 3. Install the Claude Code plugin

```bash
claude plugin install memory-access@emmahyde
```

### 4. Set up knowledge base support (optional)

To ingest external documentation as knowledge bases:

```bash
export FIRECRAWL_API_KEY=...  # Get from https://www.firecrawl.dev/
```

### 5. Verify

```bash
uv run pytest          # 174 tests pass
uv run memory-access         # server starts (MCP server mode)
uv run memory-access kb list # knowledge base CLI mode
```

## Configuration

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes* | Embedding generation via OpenAI (text-embedding-3-small) |
| `ANTHROPIC_API_KEY` | Yes* | Insight normalization via Anthropic (Claude Haiku) |
| `MEMORY_DB_PATH` | No | Database path. Default: `~/.claude/memory-access/memory.db` |
| `EMBEDDING_PROVIDER` | No | `openai` (default) or `bedrock` |
| `LLM_PROVIDER` | No | `anthropic` (default) or `bedrock` |
| `AWS_PROFILE` | No | AWS SSO profile name (required for Bedrock) |
| `AWS_REGION` | No | AWS region for Bedrock. Default: `us-east-1` |
| `BEDROCK_EMBEDDING_MODEL` | No | Bedrock model ID. Default: `amazon.titan-embed-text-v2:0` |
| `BEDROCK_LLM_MODEL` | No | Bedrock Claude model ID. Default: `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| `FIRECRAWL_API_KEY` | No | Web crawling for knowledge bases. Get from https://www.firecrawl.dev/ |
| `CRAWL_SERVICE` | No | Crawl provider. Default: `firecrawl` |
| `MIN_CONFIDENCE_THRESHOLD` | No | Minimum confidence to store ingested chunks. Default: `0.5` |

\* Not required when using `bedrock` provider.

### Claude Code

Add to your MCP settings (see `mcp-config-example.json`):

```json
{
  "mcpServers": {
    "memory-access": {
      "command": "python3",
      "args": ["-m", "memory_access.server"],
      "env": {
        "MEMORY_DB_PATH": "~/.claude/memory-access/memory.db",
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      },
      "cwd": "/path/to/memory-access/src"
    }
  }
}
```

### AWS Bedrock

To use AWS Bedrock instead of OpenAI/Anthropic APIs:

```json
{
  "mcpServers": {
    "memory-access": {
      "command": "python3",
      "args": ["-m", "memory_access.server"],
      "env": {
        "MEMORY_DB_PATH": "~/.claude/memory-access/memory.db",
        "EMBEDDING_PROVIDER": "bedrock",
        "LLM_PROVIDER": "bedrock",
        "AWS_PROFILE": "your-sso-profile",
        "AWS_REGION": "us-east-1"
      },
      "cwd": "/path/to/memory-access/src"
    }
  }
}
```

## MCP Tools (21 tools)

### Storage

- **`store_insight`** — Store text with optional domain and git context (repo, pr, author, project, task). Text is decomposed into atomic insights, classified, embedded, and indexed.
- **`update_insight`** — Update an insight's confidence score.
- **`forget`** — Delete an insight.

### Search

- **`search_insights`** — Semantic similarity search by query text. Returns ranked results.
- **`list_insights`** — List insights filtered by domain or frame.
- **`search_by_subject`** — Find insights by subject name and kind.
- **`related_insights`** — Find insights connected through shared subjects (graph traversal).

### Knowledge graph

- **`add_subject_relation`** — Create a typed edge between two subjects (e.g., `problem --solved_by--> resolution`).
- **`get_subject_relations`** — Query outgoing relations from a subject.

### Knowledge Bases

- **`add_knowledge_base`** — Create a new knowledge base by crawling or scraping a URL. Supports both full site crawling and single-page scraping with automatic ingestion and semantic indexing.
- **`search_knowledge_base`** — Search external documentation by semantic similarity. Optionally filter by KB name.
- **`list_knowledge_bases`** — List all knowledge bases with descriptions and chunk counts.

### Task orchestration

- **`create_task`** — Create a task with DB-enforced lifecycle state.
- **`assign_task_locks`** — Acquire active locks for resources (exact + path-prefix conflict detection).
- **`release_task_locks`** — Release active locks for a task (optionally scoped to resources).
- **`add_task_dependencies`** — Add dependency edges between tasks.
- **`transition_task`** — Atomically transition state with optimistic concurrency (`expected_version`).
- **`append_task_event`** — Append audit/worklog events (append-only at DB level).
- **`get_task`** — Fetch a task by ID.
- **`list_tasks`** — List tasks with optional status filter.
- **`list_task_events`** — List append-only events for a task.

## Semantic Frames

Insights are normalized into one of six canonical frames:

| Frame | Meaning | Example |
|---|---|---|
| `causal` | X causes Y | "Increasing cache TTL reduces database load" |
| `constraint` | X requires Y | "OAuth tokens must be refreshed before expiry" |
| `pattern` | When X, prefer Y | "When pagination exceeds 1000 items, use cursor-based pagination" |
| `equivalence` | X is equivalent to Y | "A mutex and a binary semaphore serve the same purpose" |
| `taxonomy` | X is a type of Y | "Rate limiting is a type of flow control" |
| `procedure` | To achieve X, do Y | "To deploy to staging, run the CI pipeline with the staging flag" |

## Subject Kinds

Insights are automatically indexed by extracted subjects:

| Kind | Source |
|---|---|
| `domain`, `entity`, `problem`, `resolution`, `context` | Extracted from text by the normalizer |
| `repo`, `pr`, `person`, `project`, `task` | From git context parameters on `store_insight` |

## Knowledge Bases

Ingest external documentation (APIs, guides, frameworks) into independently queryable knowledge bases. Create and query KBs via **CLI or MCP** — use whichever fits your workflow.

### MCP Tools

From Claude Code, use MCP tools for full KB lifecycle:

```javascript
// Create a new KB by crawling
add_knowledge_base("rails-docs", "https://guides.rubyonrails.org/association_basics.html",
                   "Rails Association Guide")

// Create a KB from a single page
add_knowledge_base("python-async", "https://docs.python.org/3/library/asyncio.html",
                   "Python asyncio docs", scrape_only=true)

// Search across all KBs
search_knowledge_base("has_many association in Rails")

// Search within a specific KB
search_knowledge_base("asyncio event loop", kb_name="python-async")

// List all KBs
list_knowledge_bases()
```

### CLI Commands

From the command line, use subcommands for KB management:

```bash
# Create a new knowledge base by crawling a URL
memory-access kb new rails-docs --crawl https://guides.rubyonrails.org/association_basics.html --description "Rails API Reference"

# Create from a single page
memory-access kb new python-async --scrape https://docs.python.org/3/library/asyncio.html

# List all knowledge bases
memory-access kb list

# Delete a knowledge base
memory-access kb delete rails-docs

# Re-crawl and refresh a knowledge base
memory-access kb refresh rails-docs --limit 100
```

### Architecture

The KB pipeline mirrors the insight storage system:

```
External docs (web)
  |
  v
Crawl → Split → Normalize → Embed → Store
```

- **Crawl**: Firecrawl extracts markdown from web pages
- **Split**: Heading-based chunking with paragraph and size fallbacks
- **Normalize**: Same LLM decomposition as insights (Claude Haiku)
- **Embed**: Same embedding engine as insights (OpenAI or Bedrock)
- **Store**: SQLite tables (`kb_chunks`) with semantic frames and subjects

KB chunks share the `subjects` index with insights, enabling cross-referencing chat memory with external docs.

## How It Works

```
User text
  |
  v
Normalizer (Claude Haiku)
  |- Decompose into atomic insights
  |- Classify: frame + subjects (entities, problems, resolutions, contexts)
  |
  v
Embedding Engine (OpenAI text-embedding-3-small)
  |- Generate L2-normalized vector
  |
  v
InsightStore (SQLite)
  |- Insert insight row
  |- Upsert subjects, link via junction table
  |- Auto-create subject relations (problem->solved_by->resolution, etc.)
  |- Auto-create insight relations (shared_subject edges)
  |- If git context: create repo/pr/person/project/task subjects + relations
```

## Development

```bash
# Run all tests (174 tests: 162 unit tests + 12 integration tests)
uv run pytest

# Run a specific test file
uv run pytest tests/test_storage.py

# Run a specific test
uv run pytest tests/test_storage.py::TestInsightStoreInit::test_initialize_creates_tables -v

# Run integration tests only
uv run pytest tests/test_kb_integration.py -v

# Generate dummy data for testing
uv run python scripts/generate_dummy_data.py
```

## Database Schema

The database has tables for insights, knowledge bases, and knowledge graphs:

### Core Tables

- **`insights`** — Chat memory: text, normalized_text, frame, subject lists (JSON arrays), embedding (float32 blob), confidence, timestamps
- **`subjects`** + **`insight_subjects`** — Subject index linking insights to named/typed subjects
- **`insight_relations`** — Weighted edges between insights (shared_subject)
- **`subject_relations`** — Typed edges between subjects (contains, scopes, solved_by, etc.)

### Knowledge Base Tables

- **`knowledge_bases`** — Registry: name, description, source_type, created_at, updated_at
- **`kb_chunks`** — Crawled and normalized chunks: text, frame, subjects, embedding, source_url, confidence
- **`kb_chunk_subjects`** — Subject index for KB chunks (same subjects as insights)
- **`kb_insight_relations`** — Optional links between KB chunks and chat insights (for cross-referencing)

### Metadata

- **`schema_versions`** — Migration tracking

Migrations run automatically on startup. Currently at version 5.

## Claude Code Plugin

This repo is also a Claude Code plugin. Install with:

```bash
claude plugin install memory-access@emmahyde
```

Includes:
- **Skill** (`using-memory-access`) — search strategy guide, subject kinds/relations reference, best practices
- **PreCompact hook** — prompts Claude to store key insights before context compaction
