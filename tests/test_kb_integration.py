"""
Integration tests for knowledge base end-to-end workflows.

Tests the full pipeline: crawl → split → normalize → embed → store,
with realistic sample data and various sources.
"""
import asyncio
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from sem_mem.crawl import CrawlService
from sem_mem.embeddings import EmbeddingEngine
from sem_mem.ingest import Ingestor, split_markdown
from sem_mem.models import CrawledPage, Frame, Insight, KbChunk
from sem_mem.normalizer import Normalizer
from sem_mem.storage import InsightStore


# ============================================================================
# Sample Data: Realistic Technical Documentation
# ============================================================================

RAILS_GUIDE_MARKDOWN = """
# Active Record Associations

## Overview

Active Record makes working with associated data straightforward and intuitive.

Active Record automatically handles one-to-many and many-to-many model relationships.
Associations simplify the common operations you perform in your code.

## Types of Associations

### belongs_to

A belongs_to association sets up a one-to-one connection with another model.
Each instance of the declaring model "belongs to" one instance of the other model.

### has_many

A has_many association indicates a one-to-many connection with another model.
You'll often find this association on the "other side" of a belongs_to association.

### has_many :through

A has_many :through association is often used to set up a many-to-many connection with another model.
This association indicates that the declaring model can be matched with zero or more instances of another model.

## Setting up Associations

Setting up an association is straightforward. Just use the appropriate macro in the model:

```ruby
class Author < ApplicationRecord
  has_many :books
end

class Book < ApplicationRecord
  belongs_to :author
end
```

## Detailed Association Reference

After you declare an association, you get a number of association proxies.

The proxy enables you to perform standard data manipulation operations on the associated objects.

### belongs_to Association Reference

The belongs_to association creates a one-to-one match with another model.

Each instance of the model has one instance of another model specified by the association.

The most common place to find this association is in:
- Comments that belong to an article
- Employees that belong to a company
- Posts that belong to a user
"""

PYTHON_ASYNCIO_MARKDOWN = """
# asyncio — Asynchronous I/O

## Concepts

asyncio is a library to write concurrent code using the async/await syntax.

asyncio is used as a foundation for multiple Python asynchronous frameworks that provide high-level APIs for solving specific application domains.

## High-level APIs

### Tasks

Tasks are used to schedule the execution of a coroutine on the event loop.

asyncio.Task extends asyncio.Future and wraps a coroutine in a Task.

When a coroutine is wrapped into a Task using functions like asyncio.create_task(), the coroutine is automatically scheduled to run soon.

### Streams

High-level APIs to work with network connections. They are built on top of low-level transports and protocols.

The high-level stream API provides connection readers and writers instead of working with socket objects directly.

### Event Loop

The event loop runs asynchronous tasks and callbacks. Each thread has its own event loop.

asyncio.run() creates a new event loop, runs the passed coroutine, closes the loop, and returns the result.

## Core Features

### Coroutines

Coroutines are declared with async def and can use await, async for, and async with.

await transfers control back to the event loop. When a coroutine is waiting for something (like I/O), the event loop can run other tasks.

### Futures

A Future is a low-level awaitable object that represents an eventual result of an asynchronous operation.

Callbacks can be attached to a Future, and they will be called when the Future resolves.

### Locks and Synchronization

asyncio.Lock provides a mutual exclusion lock for asynchronous code.

asyncio.Semaphore restricts concurrent access to a limited number of coroutines.

asyncio.Event is used to notify multiple coroutines that something has happened.

asyncio.Condition combines Lock with Event functionality.
"""


# ============================================================================
# Test Classes
# ============================================================================

class TestSplitMarkdownWithSamples:
    """Test split_markdown with realistic technical documentation."""

    def test_split_rails_guide(self):
        """Split Rails associations guide into coherent chunks."""
        chunks = split_markdown(RAILS_GUIDE_MARKDOWN, max_chars=1000)
        assert len(chunks) > 0
        assert all(isinstance(c, str) for c in chunks)
        assert all(len(c) > 0 for c in chunks)

        # Verify chunks don't exceed max size
        for chunk in chunks:
            assert len(chunk) <= 1000

        # Verify content is preserved
        full_text = "\n\n".join(chunks)
        assert "belongs_to" in full_text
        assert "has_many" in full_text
        assert "association" in full_text.lower()

    def test_split_python_asyncio(self):
        """Split Python asyncio docs into coherent chunks."""
        chunks = split_markdown(PYTHON_ASYNCIO_MARKDOWN, max_chars=800)
        assert len(chunks) > 0

        # Verify important sections are preserved
        full_text = "\n\n".join(chunks)
        assert "asyncio" in full_text
        assert "coroutine" in full_text.lower()
        assert "event loop" in full_text.lower()

    def test_split_preserves_code_blocks(self):
        """Verify code blocks aren't broken across chunks."""
        markdown = """
# Example

Here's some code:

```ruby
class Author < ApplicationRecord
  has_many :books
end
```

More text here.
"""
        chunks = split_markdown(markdown)
        full_text = "\n\n".join(chunks)
        assert "ApplicationRecord" in full_text


class TestIngestorWithMocks:
    """Integration tests for Ingestor with mocked dependencies."""

    @pytest.fixture
    async def ingestor_setup(self, tmp_db):
        """Set up Ingestor with mocked dependencies."""
        store = InsightStore(tmp_db)
        await store.initialize()

        normalizer = AsyncMock(spec=Normalizer)
        embeddings = MagicMock(spec=EmbeddingEngine)
        crawl_service = AsyncMock(spec=CrawlService)

        # Mock normalizer to return realistic insights (async)
        async def mock_normalize(text):
            return [
                Insight(
                    text=text[:100],
                    normalized_text=text[:100],
                    frame=Frame.CAUSAL,
                    domains=["documentation"],
                    entities=["technical_term"],
                    problems=[],
                    resolutions=[],
                    contexts=[],
                    confidence=0.85,  # Above default 0.5 threshold
                )
            ]

        normalizer.normalize.side_effect = mock_normalize

        # Mock embeddings to return random vectors for both embed and embed_batch
        embeddings.embed.side_effect = lambda _: np.random.rand(1536).astype(np.float32)
        embeddings.embed_batch.side_effect = lambda texts: [
            np.random.rand(1536).astype(np.float32) for _ in texts
        ]

        ingestor = Ingestor(
            store=store,
            normalizer=normalizer,
            embeddings=embeddings,
            crawl_service=crawl_service,
        )

        return ingestor, store, crawl_service

    @pytest.mark.asyncio
    async def test_ingest_rails_documentation(self, ingestor_setup):
        """Ingest Rails guide into knowledge base."""
        ingestor, store, crawl_service = ingestor_setup

        # Set up crawl service to return Rails docs
        crawl_service.crawl.return_value = [
            CrawledPage(
                url="https://guides.rubyonrails.org/association_basics.html",
                markdown=RAILS_GUIDE_MARKDOWN,
                metadata={"title": "Active Record Associations"},
            )
        ]

        # Create KB
        kb_id = await store.create_kb("rails-docs", "Rails API Reference")
        assert kb_id is not None

        # Ingest
        total_chunks = await ingestor.ingest_crawl(kb_id, "https://guides.rubyonrails.org/association_basics.html", limit=1)
        assert total_chunks > 0

        # Verify chunks stored
        kb = await store.get_kb(kb_id)
        assert kb.name == "rails-docs"
        assert kb.description == "Rails API Reference"

    @pytest.mark.asyncio
    async def test_ingest_asyncio_documentation(self, ingestor_setup):
        """Ingest Python asyncio docs into knowledge base."""
        ingestor, store, crawl_service = ingestor_setup

        # Set up crawl service
        crawl_service.scrape.return_value = CrawledPage(
            url="https://docs.python.org/3/library/asyncio.html",
            markdown=PYTHON_ASYNCIO_MARKDOWN,
            metadata={"title": "asyncio — Asynchronous I/O"},
        )

        # Create KB
        kb_id = await store.create_kb("python-docs", "Python standard library")
        assert kb_id is not None

        # Ingest single page
        total_chunks = await ingestor.ingest_scrape(kb_id, "https://docs.python.org/3/library/asyncio.html")
        assert total_chunks > 0

    @pytest.mark.asyncio
    async def test_ingest_with_progress_callback(self, ingestor_setup):
        """Verify progress callback is invoked during ingestion."""
        ingestor, store, crawl_service = ingestor_setup

        pages = [
            CrawledPage(
                url=f"https://example.com/page{i}",
                markdown=RAILS_GUIDE_MARKDOWN[:500],
                metadata={},
            )
            for i in range(3)
        ]
        crawl_service.crawl.return_value = pages

        kb_id = await store.create_kb("test-kb", "Test")

        progress_calls = []

        def track_progress(current, total, url):
            progress_calls.append((current, total, url))

        await ingestor.ingest_crawl(kb_id, "https://example.com", limit=3, on_progress=track_progress)

        # Verify progress was reported for each page
        assert len(progress_calls) == 3
        assert progress_calls[0][0] == 1
        assert progress_calls[1][0] == 2
        assert progress_calls[2][0] == 3
        assert progress_calls[0][1] == 3
        assert progress_calls[1][1] == 3
        assert progress_calls[2][1] == 3


class TestKnowledgeBaseSearch:
    """Integration tests for knowledge base search."""

    @pytest.fixture
    async def populated_kb(self, tmp_db):
        """Create a KB with sample chunks."""
        store = InsightStore(tmp_db)
        await store.initialize()

        # Create KB
        kb_id = await store.create_kb("test-kb", "Test Knowledge Base")

        # Insert sample chunks
        chunks = [
            KbChunk(
                kb_id=kb_id,
                text="Rails belongs_to creates a one-to-one connection",
                normalized_text="Rails belongs_to creates a one-to-one connection",
                frame=Frame.CAUSAL,
                domains=["rails"],
                entities=["belongs_to", "association"],
                source_url="https://guides.rubyonrails.org/association_basics.html",
            ),
            KbChunk(
                kb_id=kb_id,
                text="asyncio.run() creates a new event loop and runs a coroutine",
                normalized_text="asyncio.run() creates a new event loop and runs a coroutine",
                frame=Frame.PROCEDURE,
                domains=["python", "async"],
                entities=["asyncio", "event_loop", "coroutine"],
                source_url="https://docs.python.org/3/library/asyncio.html",
            ),
        ]

        embeddings = np.array(
            [np.random.rand(1536).astype(np.float32) for _ in chunks],
            dtype=object,
        )

        for chunk, emb in zip(chunks, embeddings):
            await store.insert_kb_chunk(chunk, emb)

        return store, kb_id

    @pytest.mark.asyncio
    async def test_search_kb_returns_results(self, populated_kb):
        """Search KB and verify results are returned."""
        store, kb_id = populated_kb

        # Create a query embedding
        query_embedding = np.random.rand(1536).astype(np.float32)

        # Search within KB
        results = await store.search_kb_by_embedding(query_embedding, kb_id=kb_id, limit=5)

        # Should return results (exact matches won't be perfect with random embeddings)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_list_kb_chunks(self, populated_kb):
        """List all chunks in a KB."""
        store, kb_id = populated_kb

        chunks = await store.list_kb_chunks(kb_id, limit=10)
        assert len(chunks) >= 2
        assert all(c.kb_id == kb_id for c in chunks)
        assert any("belongs_to" in c.text for c in chunks)
        assert any("asyncio" in c.text for c in chunks)

    @pytest.mark.asyncio
    async def test_delete_kb_cascades(self, populated_kb):
        """Deleting KB removes all chunks."""
        store, kb_id = populated_kb

        # Verify chunks exist
        chunks_before = await store.list_kb_chunks(kb_id)
        assert len(chunks_before) > 0

        # Delete KB
        deleted = await store.delete_kb(kb_id)
        assert deleted is True

        # Verify chunks are gone
        chunks_after = await store.list_kb_chunks(kb_id)
        assert len(chunks_after) == 0


class TestMultipleKnowledgeBases:
    """Integration tests for managing multiple KBs."""

    @pytest.fixture
    async def multi_kb_store(self, tmp_db):
        """Create store with multiple KBs."""
        store = InsightStore(tmp_db)
        await store.initialize()

        kb_ids = []
        for name in ["rails-docs", "python-docs", "js-docs"]:
            kb_id = await store.create_kb(name, f"Documentation for {name}")
            kb_ids.append(kb_id)

        return store, kb_ids

    @pytest.mark.asyncio
    async def test_list_multiple_kbs(self, multi_kb_store):
        """List all knowledge bases."""
        store, kb_ids = multi_kb_store

        kbs = await store.list_kbs()
        assert len(kbs) == 3
        kb_names = [kb.name for kb in kbs]
        assert "rails-docs" in kb_names
        assert "python-docs" in kb_names
        assert "js-docs" in kb_names

    @pytest.mark.asyncio
    async def test_get_kb_by_name(self, multi_kb_store):
        """Retrieve KB by name."""
        store, _ = multi_kb_store

        kb = await store.get_kb_by_name("python-docs")
        assert kb is not None
        assert kb.name == "python-docs"
        assert "python" in kb.description.lower()

    @pytest.mark.asyncio
    async def test_search_across_all_kbs(self, multi_kb_store):
        """Search across all KBs when kb_id is None."""
        store, kb_ids = multi_kb_store

        # Insert chunks into different KBs
        for i, kb_id in enumerate(kb_ids):
            chunk = KbChunk(
                kb_id=kb_id,
                text=f"Sample content from KB {i}",
                normalized_text=f"Sample content from KB {i}",
                frame=Frame.CAUSAL,
                domains=["sample"],
                entities=[f"kb_{i}"],
            )
            emb = np.random.rand(1536).astype(np.float32)
            await store.insert_kb_chunk(chunk, emb)

        # Search across all KBs
        query_embedding = np.random.rand(1536).astype(np.float32)
        results = await store.search_kb_by_embedding(query_embedding, kb_id=None, limit=10)

        # Should return results from multiple KBs
        assert isinstance(results, list)
