# Knowledge Bases Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add independently queryable "knowledge bases" for ingesting external documentation (e.g., Rails docs) into memory-access's existing semantic memory infrastructure.

**Architecture:** A `knowledge_bases` registry + `kb_chunks` table mirrors the `insights` schema minus git context. Chunks share the existing `subjects` system for cross-referencing with chat memory. A `CrawlService` abstraction with a Firecrawl default handles web crawling. An `Ingestor` class orchestrates crawl → split → normalize → embed → store. CLI commands manage KB lifecycle; MCP tools enable mid-conversation querying.

**Tech Stack:** firecrawl-py (crawling), existing normalizer/embeddings/storage, click or argparse (CLI subcommands)

---

### Task 1: Models

**Files:**
- Modify: `src/memory_access/models.py`
- Test: `tests/test_models.py`

**Step 1: Add new model classes to `models.py`**

```python
class KnowledgeBase(BaseModel):
    """A collection of document chunks from an external source."""
    id: Optional[str] = None
    name: str
    description: str = ""
    source_type: str = ""  # 'crawl', 'scrape', 'file', 'text'
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class KbChunk(BaseModel):
    """A normalized chunk from a knowledge base document."""
    id: Optional[str] = None
    kb_id: str
    text: str
    normalized_text: str = ""
    frame: Frame = Frame.CAUSAL
    domains: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)
    resolutions: list[str] = Field(default_factory=list)
    contexts: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    source_url: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CrawledPage(BaseModel):
    """A single page returned by a crawl service."""
    url: str
    markdown: str
    metadata: dict = Field(default_factory=dict)
```

**Step 2: Add tests to `tests/test_models.py`**

Test construction of each new model, default values, and that `KbChunk` mirrors `Insight` field structure (minus git context). Test `CrawledPage` with metadata.

**Step 3: Commit**

```bash
git add src/memory_access/models.py tests/test_models.py
git commit -m "feat: add KnowledgeBase, KbChunk, CrawledPage models"
```

---

### Task 2: Storage Migration + KB CRUD

**Files:**
- Modify: `src/memory_access/storage.py`
- Test: `tests/test_storage.py`

**Step 1: Add migration 005 to `storage.py`**

Add `_migrate_005_knowledge_bases` following the existing pattern. Creates tables: `knowledge_bases`, `kb_chunks`, `kb_chunk_subjects`, `kb_insight_relations`. Register it in `InsightStore.__init__` migrations list.

```sql
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_name ON knowledge_bases(name);

CREATE TABLE IF NOT EXISTS kb_chunks (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    frame TEXT NOT NULL,
    domains TEXT NOT NULL DEFAULT '[]',
    entities TEXT NOT NULL DEFAULT '[]',
    problems TEXT NOT NULL DEFAULT '[]',
    resolutions TEXT NOT NULL DEFAULT '[]',
    contexts TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 1.0,
    source_url TEXT NOT NULL DEFAULT '',
    embedding BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_kb_id ON kb_chunks(kb_id);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_frame ON kb_chunks(frame);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_source_url ON kb_chunks(source_url);

CREATE TABLE IF NOT EXISTS kb_chunk_subjects (
    kb_chunk_id TEXT NOT NULL REFERENCES kb_chunks(id) ON DELETE CASCADE,
    subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    PRIMARY KEY (kb_chunk_id, subject_id)
);
CREATE INDEX IF NOT EXISTS idx_kb_chunk_subjects_subject ON kb_chunk_subjects(subject_id);

CREATE TABLE IF NOT EXISTS kb_insight_relations (
    kb_chunk_id TEXT NOT NULL REFERENCES kb_chunks(id) ON DELETE CASCADE,
    insight_id TEXT NOT NULL REFERENCES insights(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (kb_chunk_id, insight_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_kb_insight_rel_chunk ON kb_insight_relations(kb_chunk_id);
CREATE INDEX IF NOT EXISTS idx_kb_insight_rel_insight ON kb_insight_relations(insight_id);
CREATE INDEX IF NOT EXISTS idx_kb_insight_rel_type ON kb_insight_relations(relation_type);
```

**Step 2: Add KB CRUD methods to `InsightStore`**

Methods to add:
- `create_kb(name, description, source_type) -> str` — returns KB id
- `get_kb(kb_id) -> KnowledgeBase | None`
- `get_kb_by_name(name) -> KnowledgeBase | None`
- `list_kbs() -> list[KnowledgeBase]`
- `delete_kb(kb_id) -> bool` — cascading delete (all chunks, subjects, relations)

**Step 3: Add KB chunk methods to `InsightStore`**

Methods to add:
- `insert_kb_chunk(chunk: KbChunk, embedding, ...) -> str` — mirrors `insert()` but for kb_chunks table; also calls `_upsert_kb_chunk_subjects` to link subjects
- `search_kb_by_embedding(query_embedding, kb_id=None, limit=5) -> list[SearchResult]` — cosine similarity search over kb_chunks; if kb_id is None, search all KBs
- `list_kb_chunks(kb_id, limit=20) -> list[KbChunk]`
- `delete_kb_chunks(kb_id) -> int` — delete all chunks for a KB (for refresh)

Also add:
- `_upsert_kb_chunk_subjects(db, chunk_id, chunk: KbChunk)` — mirrors `_upsert_subjects` but writes to `kb_chunk_subjects`
- `_row_to_kb_chunk(row) -> KbChunk` — mirrors `_row_to_insight`
- `_row_to_knowledge_base(row) -> KnowledgeBase`

**Step 4: Add tests to `tests/test_storage.py`**

Test classes to add:
- `TestKBMigration` — verify tables created on initialize
- `TestKBCrud` — create, get, get_by_name, list, delete
- `TestKBChunkInsert` — insert chunk, verify subjects linked
- `TestKBChunkSearch` — embedding search within a KB, across all KBs
- `TestKBChunkDelete` — cascading delete removes chunks and subject links

Use the existing `tmp_db` fixture. Create test embeddings with `np.random.rand(1536).astype(np.float32)`.

**Step 5: Commit**

```bash
git add src/memory_access/storage.py tests/test_storage.py
git commit -m "feat: add knowledge_bases migration and storage methods"
```

---

### Task 3: Crawl Service Abstraction + Firecrawl Implementation

**Files:**
- Create: `src/memory_access/crawl.py`
- Test: `tests/test_crawl.py`
- Modify: `pyproject.toml` (add `firecrawl-py` dependency)

**Step 1: Add `firecrawl-py` to `pyproject.toml` dependencies**

Add `"firecrawl-py>=1.0.0"` to the `dependencies` list.

**Step 2: Create `src/memory_access/crawl.py`**

```python
from __future__ import annotations

import os
from abc import ABC, abstractmethod

from .models import CrawledPage


class CrawlService(ABC):
    """Abstract crawl service. Implement for each crawl provider."""

    @abstractmethod
    async def crawl(self, url: str, limit: int = 1000) -> list[CrawledPage]:
        """Crawl a URL and return pages as markdown."""
        ...

    @abstractmethod
    async def scrape(self, url: str) -> CrawledPage:
        """Scrape a single URL and return as markdown."""
        ...


class FirecrawlService(CrawlService):
    """Crawl service using Firecrawl API."""

    def __init__(self, api_key: str | None = None):
        from firecrawl import FirecrawlApp
        self.app = FirecrawlApp(api_key=api_key or os.environ.get("FIRECRAWL_API_KEY"))

    async def crawl(self, url: str, limit: int = 1000) -> list[CrawledPage]:
        """Crawl a URL using Firecrawl. Returns markdown pages."""
        result = self.app.crawl_url(
            url,
            params={
                "limit": limit,
                "scrapeOptions": {
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                },
            },
        )
        pages = []
        for item in result.data:
            pages.append(CrawledPage(
                url=item.metadata.get("sourceURL", url),
                markdown=item.markdown or "",
                metadata=item.metadata or {},
            ))
        return pages

    async def scrape(self, url: str) -> CrawledPage:
        """Scrape a single URL using Firecrawl."""
        result = self.app.scrape_url(
            url,
            params={"formats": ["markdown"], "onlyMainContent": True},
        )
        return CrawledPage(
            url=result.metadata.get("sourceURL", url),
            markdown=result.markdown or "",
            metadata=result.metadata or {},
        )


def create_crawl_service(
    provider: str | None = None, **kwargs
) -> CrawlService:
    """Factory to create the appropriate crawl service."""
    provider = provider or os.environ.get("CRAWL_SERVICE", "firecrawl")
    if provider == "firecrawl":
        return FirecrawlService(**kwargs)
    raise ValueError(f"Unknown crawl service: {provider}")
```

Note: The Firecrawl SDK's `crawl_url` is synchronous (it polls internally). The async wrapper is thin — if we need true async later, we can run it in a thread executor. Fine for MVP.

**Important:** Check the actual `firecrawl-py` SDK response shape — the field access pattern above (`result.data`, `item.markdown`, `item.metadata`) needs to match the real SDK. The subagent implementing this should `pip install firecrawl-py` and verify the API shape, or read the SDK source.

**Step 3: Add tests to `tests/test_crawl.py`**

Test the factory function returns correct service type. Mock `FirecrawlApp` for unit tests:
- `TestCreateCrawlService` — factory returns `FirecrawlService` by default, raises for unknown provider
- `TestFirecrawlService` — mock `FirecrawlApp.crawl_url` and `scrape_url`, verify `CrawledPage` construction

**Step 4: Commit**

```bash
git add src/memory_access/crawl.py tests/test_crawl.py pyproject.toml
git commit -m "feat: add CrawlService abstraction with Firecrawl implementation"
```

---

### Task 4: Ingestor (Crawl → Split → Normalize → Embed → Store)

**Files:**
- Create: `src/memory_access/ingest.py`
- Test: `tests/test_ingest.py`

**Step 1: Create `src/memory_access/ingest.py`**

```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .crawl import CrawlService
from .embeddings import EmbeddingEngine, BedrockEmbeddingEngine
from .models import CrawledPage, KbChunk
from .normalizer import Normalizer
from .storage import InsightStore


def split_markdown(text: str, max_chars: int = 4000) -> list[str]:
    """Split markdown into chunks by ## headings, with max_chars fallback.

    Strategy:
    1. Split on ## headings — each section becomes a chunk
    2. If a section exceeds max_chars, split on paragraphs (double newline)
    3. If a paragraph still exceeds max_chars, split at max_chars boundary
    """
    if not text.strip():
        return []

    # Split on ## headings, preserving the heading with its content
    sections = []
    current = []
    for line in text.split("\n"):
        if line.startswith("## ") and current:
            sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current))

    # Sub-split oversized sections
    chunks = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section)
        else:
            # Split on paragraphs
            paragraphs = section.split("\n\n")
            current_chunk = ""
            for para in paragraphs:
                if len(current_chunk) + len(para) + 2 > max_chars:
                    if current_chunk:
                        chunks.append(current_chunk)
                    # Handle single paragraphs exceeding max_chars
                    if len(para) > max_chars:
                        for i in range(0, len(para), max_chars):
                            chunks.append(para[i:i + max_chars])
                        current_chunk = ""
                    else:
                        current_chunk = para
                else:
                    current_chunk = current_chunk + "\n\n" + para if current_chunk else para
            if current_chunk:
                chunks.append(current_chunk)

    return [c.strip() for c in chunks if c.strip()]


class Ingestor:
    """Orchestrates: crawl → split → normalize → embed → store."""

    def __init__(
        self,
        store: InsightStore,
        normalizer: Normalizer,
        embeddings: EmbeddingEngine | BedrockEmbeddingEngine,
        crawl_service: CrawlService,
    ):
        self.store = store
        self.normalizer = normalizer
        self.embeddings = embeddings
        self.crawl_service = crawl_service

    async def ingest_crawl(
        self,
        kb_id: str,
        url: str,
        limit: int = 1000,
        on_progress: callable | None = None,
    ) -> int:
        """Crawl a URL and ingest all pages into a knowledge base.

        Returns the total number of chunks stored.
        """
        pages = await self.crawl_service.crawl(url, limit=limit)
        total_chunks = 0

        for i, page in enumerate(pages):
            if on_progress:
                on_progress(i + 1, len(pages), page.url)

            chunks_stored = await self.ingest_page(kb_id, page)
            total_chunks += chunks_stored

        return total_chunks

    async def ingest_page(self, kb_id: str, page: CrawledPage) -> int:
        """Ingest a single crawled page into a knowledge base.

        Returns the number of chunks stored.
        """
        text_chunks = split_markdown(page.markdown)
        stored = 0

        for chunk_text in text_chunks:
            insights = await self.normalizer.normalize(chunk_text)
            for insight in insights:
                emb = self.embeddings.embed(insight.normalized_text)
                kb_chunk = KbChunk(
                    kb_id=kb_id,
                    text=insight.text,
                    normalized_text=insight.normalized_text,
                    frame=insight.frame,
                    domains=insight.domains,
                    entities=insight.entities,
                    problems=insight.problems,
                    resolutions=insight.resolutions,
                    contexts=insight.contexts,
                    confidence=insight.confidence,
                    source_url=page.url,
                )
                await self.store.insert_kb_chunk(kb_chunk, emb)
                stored += 1

        return stored

    async def ingest_scrape(self, kb_id: str, url: str) -> int:
        """Scrape a single URL and ingest into a knowledge base."""
        page = await self.crawl_service.scrape(url)
        return await self.ingest_page(kb_id, page)
```

**Step 2: Add tests to `tests/test_ingest.py`**

Test classes:
- `TestSplitMarkdown` — test heading-based splitting, oversized sections, empty input, no headings, paragraphs fallback. This is pure logic, no mocks needed.
- `TestIngestor` — mock crawl_service, normalizer, embeddings, and store. Verify `ingest_crawl` calls crawl, splits, normalizes, embeds, stores. Verify `ingest_page` processes a single page correctly. Verify progress callback is called.

**Step 3: Commit**

```bash
git add src/memory_access/ingest.py tests/test_ingest.py
git commit -m "feat: add Ingestor with crawl → split → normalize → embed → store pipeline"
```

---

### Task 5: SemMemApp KB Methods + MCP Tools

**Files:**
- Modify: `src/memory_access/server.py`
- Modify: `tests/test_server.py`

**Step 1: Add KB methods to `SemMemApp`**

Add to the class:
- `search_knowledge_base(query, kb_name="", limit=5) -> str` — embed query, search kb_chunks (optionally filtered by KB name via `get_kb_by_name`), format results
- `list_knowledge_bases() -> str` — list all KBs with descriptions and chunk counts

**Step 2: Update `create_app` to accept crawl service config**

Add `crawl_service` parameter to `create_app()`. Store on `SemMemApp` for use by CLI (not by MCP tools directly — ingestion happens via CLI, not MCP).

**Step 3: Add MCP tools to `create_mcp_server`**

```python
@mcp.tool()
async def search_knowledge_base(query: str, kb_name: str = "", limit: int = 5) -> str:
    """Search for relevant content in knowledge bases by semantic similarity.
    Searches within a specific knowledge base if kb_name is provided,
    or across all knowledge bases if omitted."""
    ...

@mcp.tool()
async def list_knowledge_bases() -> str:
    """List all available knowledge bases with their descriptions and chunk counts."""
    ...
```

**Step 4: Add tests to `tests/test_server.py`**

Test the new `SemMemApp` methods with mocked store/embeddings. Verify `search_knowledge_base` formats results correctly. Verify `list_knowledge_bases` returns formatted list.

**Step 5: Commit**

```bash
git add src/memory_access/server.py tests/test_server.py
git commit -m "feat: add search_knowledge_base and list_knowledge_bases MCP tools"
```

---

### Task 6: CLI Commands

**Files:**
- Create: `src/memory_access/cli.py`
- Modify: `pyproject.toml` (update scripts entry)
- Test: `tests/test_cli.py`

**Step 1: Create `src/memory_access/cli.py`**

Use `argparse` (no new dependency). Subcommand structure:

```
memory-access                          # existing: runs MCP server
memory-access kb new <name> --crawl <url> [--scrape <url>] [--limit N] [--description "..."]
memory-access kb list
memory-access kb delete <name>
memory-access kb refresh <name>        # re-crawl: delete chunks, re-ingest
```

Implementation approach:
- `cli.py` has a `main()` that checks `sys.argv` for `kb` subcommand
- If no `kb` subcommand, delegate to existing `server:main` (MCP server)
- Each subcommand is an async function that creates the app, crawl service, and ingestor
- Progress reporting via print to stderr

```python
import argparse
import asyncio
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "kb":
        return _run_kb_cli()

    # Default: run MCP server
    from .server import main as server_main
    server_main()


def _run_kb_cli():
    parser = argparse.ArgumentParser(prog="memory-access kb")
    sub = parser.add_subparsers(dest="command", required=True)

    # new
    new_p = sub.add_parser("new", help="Create a new knowledge base")
    new_p.add_argument("name", help="Knowledge base name (slug)")
    new_p.add_argument("--crawl", help="URL to crawl")
    new_p.add_argument("--scrape", help="Single URL to scrape")
    new_p.add_argument("--limit", type=int, default=1000, help="Max pages to crawl")
    new_p.add_argument("--description", default="", help="KB description")

    # list
    sub.add_parser("list", help="List knowledge bases")

    # delete
    del_p = sub.add_parser("delete", help="Delete a knowledge base")
    del_p.add_argument("name", help="Knowledge base name")

    # refresh
    ref_p = sub.add_parser("refresh", help="Re-crawl and refresh a knowledge base")
    ref_p.add_argument("name", help="Knowledge base name")
    ref_p.add_argument("--limit", type=int, default=1000, help="Max pages to crawl")

    args = parser.parse_args(sys.argv[2:])
    asyncio.run(_dispatch(args))


async def _dispatch(args):
    from .server import create_app
    from .crawl import create_crawl_service
    from .ingest import Ingestor

    app = await create_app()
    crawl = create_crawl_service()
    ingestor = Ingestor(
        store=app.store,
        normalizer=app.normalizer,
        embeddings=app.embeddings,
        crawl_service=crawl,
    )

    if args.command == "new":
        await _cmd_new(app, ingestor, args)
    elif args.command == "list":
        await _cmd_list(app)
    elif args.command == "delete":
        await _cmd_delete(app, args)
    elif args.command == "refresh":
        await _cmd_refresh(app, ingestor, args)
```

Implement each `_cmd_*` function:
- `_cmd_new`: create KB via store, then ingest_crawl or ingest_scrape, print progress + summary
- `_cmd_list`: list KBs, print as table
- `_cmd_delete`: get KB by name, delete, print confirmation
- `_cmd_refresh`: get KB by name, delete chunks, re-crawl, print progress + summary

**Step 2: Update `pyproject.toml` scripts**

Change `memory-access = "memory_access.server:main"` to `memory-access = "memory_access.cli:main"`

**Step 3: Add tests to `tests/test_cli.py`**

Test argument parsing for each subcommand. Mock the app/ingestor for integration tests. Verify `_cmd_new` creates KB and calls ingestor. Verify `_cmd_list` formats output. Verify `_cmd_delete` deletes by name.

**Step 4: Commit**

```bash
git add src/memory_access/cli.py tests/test_cli.py pyproject.toml
git commit -m "feat: add memory-access kb CLI commands for knowledge base management"
```

---

### Task 7: Module Wiring + Exports

**Files:**
- Modify: `src/memory_access/__init__.py`

**Step 1: Update `__init__.py`**

Add exports for new modules: `crawl`, `ingest`, `cli`. Ensure imports work.

**Step 2: Run `uv sync --group dev`**

Install the new `firecrawl-py` dependency.

**Step 3: Commit**

```bash
git add src/memory_access/__init__.py
git commit -m "chore: wire up new KB modules and install firecrawl-py"
```

---

## Environment Variables (new)

| Variable | Default | Purpose |
|----------|---------|---------|
| `FIRECRAWL_API_KEY` | — | Required for crawl/scrape operations |
| `CRAWL_SERVICE` | `firecrawl` | Crawl provider selection |

## File Summary

| File | Action | Purpose |
|------|--------|---------|
| `src/memory_access/models.py` | Modify | Add KnowledgeBase, KbChunk, CrawledPage |
| `src/memory_access/storage.py` | Modify | Migration 005 + KB CRUD + chunk methods |
| `src/memory_access/crawl.py` | Create | CrawlService abstraction + FirecrawlService |
| `src/memory_access/ingest.py` | Create | Ingestor pipeline + split_markdown |
| `src/memory_access/server.py` | Modify | KB search/list methods + MCP tools |
| `src/memory_access/cli.py` | Create | CLI subcommands for KB management |
| `src/memory_access/__init__.py` | Modify | Wire up new modules |
| `pyproject.toml` | Modify | Add firecrawl-py dep, update scripts entry |
| `tests/test_models.py` | Modify | KnowledgeBase/KbChunk/CrawledPage tests |
| `tests/test_storage.py` | Modify | Migration + KB CRUD + chunk search tests |
| `tests/test_crawl.py` | Create | CrawlService factory + Firecrawl mock tests |
| `tests/test_ingest.py` | Create | split_markdown + Ingestor mock tests |
| `tests/test_server.py` | Modify | KB MCP tool tests |
| `tests/test_cli.py` | Create | CLI argument parsing + command tests |
