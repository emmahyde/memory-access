# semantic-memory

An MCP server that gives AI agents persistent, intent-based memory. Text is decomposed into atomic insights, classified into semantic frames, embedded as vectors, and stored in a SQLite knowledge graph with subject indexing.

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/emmahyde/brainspace.git
cd brainspace
uv sync --group dev
```

Or install from PyPI:

```bash
pip install sem-mem
# or
uv add sem-mem
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
claude plugin install semantic-memory@brainspace
```

### 4. Verify

```bash
uv run pytest          # 85 tests pass
uv run semantic-memory # server starts
```

## Configuration

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes* | Embedding generation via OpenAI (text-embedding-3-small) |
| `ANTHROPIC_API_KEY` | Yes* | Insight normalization via Anthropic (Claude Haiku) |
| `MEMORY_DB_PATH` | No | Database path. Default: `~/.claude/semantic-memory/memory.db` |
| `EMBEDDING_PROVIDER` | No | `openai` (default) or `bedrock` |
| `LLM_PROVIDER` | No | `anthropic` (default) or `bedrock` |
| `AWS_PROFILE` | No | AWS SSO profile name (required for Bedrock) |
| `AWS_REGION` | No | AWS region for Bedrock. Default: `us-east-1` |
| `BEDROCK_EMBEDDING_MODEL` | No | Bedrock model ID. Default: `amazon.titan-embed-text-v2:0` |
| `BEDROCK_LLM_MODEL` | No | Bedrock Claude model ID. Default: `us.anthropic.claude-haiku-4-5-20251001-v1:0` |

\* Not required when using `bedrock` provider.

### Claude Code

Add to your MCP settings (see `mcp-config-example.json`):

```json
{
  "mcpServers": {
    "semantic-memory": {
      "command": "python3",
      "args": ["-m", "semantic_memory.server"],
      "env": {
        "MEMORY_DB_PATH": "~/.claude/semantic-memory/memory.db",
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      },
      "cwd": "/path/to/semantic-memory/src"
    }
  }
}
```

### AWS Bedrock

To use AWS Bedrock instead of OpenAI/Anthropic APIs:

```json
{
  "mcpServers": {
    "semantic-memory": {
      "command": "python3",
      "args": ["-m", "semantic_memory.server"],
      "env": {
        "MEMORY_DB_PATH": "~/.claude/semantic-memory/memory.db",
        "EMBEDDING_PROVIDER": "bedrock",
        "LLM_PROVIDER": "bedrock",
        "AWS_PROFILE": "your-sso-profile",
        "AWS_REGION": "us-east-1"
      },
      "cwd": "/path/to/semantic-memory/src"
    }
  }
}
```

## MCP Tools

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
# Run all tests (85 tests)
uv run pytest

# Run a specific test file
uv run pytest tests/test_storage.py

# Run a specific test
uv run pytest tests/test_storage.py::TestInsightStoreInit::test_initialize_creates_tables -v

# Generate dummy data for testing
uv run python scripts/generate_dummy_data.py
```

## Database Schema

The database has four main tables plus a migration tracker:

- **`insights`** — Core storage: text, normalized_text, frame, subject lists (JSON arrays), embedding (float32 blob), confidence, timestamps
- **`subjects`** + **`insight_subjects`** — Subject index linking insights to named/typed subjects
- **`insight_relations`** — Weighted edges between insights (shared_subject)
- **`subject_relations`** — Typed edges between subjects (contains, scopes, solved_by, etc.)
- **`schema_versions`** — Migration tracking

Migrations run automatically on startup. Currently at version 4.

## Claude Code Plugin

This repo is also a Claude Code plugin. Install with:

```bash
claude plugin install semantic-memory@brainspace
```

Includes:
- **Skill** (`using-semantic-memory`) — search strategy guide, subject kinds/relations reference, best practices
- **PreCompact hook** — prompts Claude to store key insights before context compaction
