import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock
from memory_access.ingest import split_markdown, Ingestor
from memory_access.models import CrawledPage, Frame, Insight


class TestSplitMarkdown:
    def test_empty_input(self):
        assert split_markdown("") == []
        assert split_markdown("   ") == []

    def test_no_headings(self):
        text = "Just a paragraph of text."
        result = split_markdown(text)
        assert len(result) == 1
        assert result[0] == "Just a paragraph of text."

    def test_splits_on_h2_headings(self):
        text = "# Title\n\nIntro paragraph.\n\n## Section 1\n\nContent 1.\n\n## Section 2\n\nContent 2."
        result = split_markdown(text)
        assert len(result) == 3
        assert "# Title" in result[0]
        assert "## Section 1" in result[1]
        assert "## Section 2" in result[2]

    def test_oversized_section_splits_on_paragraphs(self):
        # Create a section with two paragraphs that together exceed max_chars
        para1 = "A" * 30
        para2 = "B" * 30
        text = f"{para1}\n\n{para2}"
        result = split_markdown(text, max_chars=40)
        assert len(result) == 2
        assert result[0] == para1
        assert result[1] == para2

    def test_oversized_paragraph_splits_at_boundary(self):
        text = "X" * 100
        result = split_markdown(text, max_chars=40)
        assert len(result) == 3
        assert result[0] == "X" * 40
        assert result[1] == "X" * 40
        assert result[2] == "X" * 20

    def test_strips_whitespace(self):
        text = "  \n## Section\n\n  Content  \n\n"
        result = split_markdown(text)
        assert all(c == c.strip() for c in result)

    def test_multiple_headings_preserves_content(self):
        text = "## A\n\nContent A\n\n## B\n\nContent B\n\n## C\n\nContent C"
        result = split_markdown(text)
        assert len(result) == 3
        assert "Content A" in result[0]
        assert "Content B" in result[1]
        assert "Content C" in result[2]


class TestIngestor:
    def _make_ingestor(self):
        store = MagicMock()
        store.insert_kb_chunk = AsyncMock(return_value="chunk-id")
        normalizer = MagicMock()
        embeddings = MagicMock()
        crawl_service = MagicMock()
        return Ingestor(
            store=store,
            normalizer=normalizer,
            embeddings=embeddings,
            crawl_service=crawl_service,
        )

    async def test_ingest_page_processes_chunks(self):
        ingestor = self._make_ingestor()
        insight = Insight(
            text="test",
            normalized_text="normalized test",
            frame=Frame.CAUSAL,
            domains=["python"],
            confidence=0.8,
        )
        ingestor.normalizer.normalize = AsyncMock(return_value=[insight])
        ingestor.embeddings.embed_batch = MagicMock(
            return_value=np.zeros((1, 128), dtype=np.float32)
        )

        page = CrawledPage(url="https://example.com", markdown="## Section\n\nSome content here.")
        count = await ingestor.ingest_page("kb-123", page)

        assert count == 1
        ingestor.normalizer.normalize.assert_called_once()
        ingestor.embeddings.embed_batch.assert_called_once_with(["normalized test"])
        ingestor.store.insert_kb_chunk.assert_called_once()

    async def test_ingest_crawl_processes_all_pages(self):
        ingestor = self._make_ingestor()
        insight = Insight(text="t", normalized_text="n", frame=Frame.CAUSAL, confidence=0.8)
        ingestor.normalizer.normalize = AsyncMock(return_value=[insight])
        ingestor.embeddings.embed_batch = MagicMock(
            return_value=np.zeros((1, 128), dtype=np.float32)
        )
        ingestor.crawl_service.crawl = AsyncMock(return_value=[
            CrawledPage(url="https://example.com/1", markdown="## A\n\nContent"),
            CrawledPage(url="https://example.com/2", markdown="## B\n\nContent"),
        ])

        count = await ingestor.ingest_crawl("kb-123", "https://example.com", limit=10)
        assert count == 2
        assert ingestor.crawl_service.crawl.call_count == 1

    async def test_ingest_crawl_calls_progress(self):
        ingestor = self._make_ingestor()
        insight = Insight(text="t", normalized_text="n", frame=Frame.CAUSAL, confidence=0.8)
        ingestor.normalizer.normalize = AsyncMock(return_value=[insight])
        ingestor.embeddings.embed_batch = MagicMock(
            return_value=np.zeros((1, 128), dtype=np.float32)
        )
        ingestor.crawl_service.crawl = AsyncMock(return_value=[
            CrawledPage(url="https://example.com/1", markdown="## A\n\nContent"),
        ])

        progress_calls = []
        def on_progress(current, total, url):
            progress_calls.append((current, total, url))

        await ingestor.ingest_crawl("kb-123", "https://example.com", on_progress=on_progress)
        assert len(progress_calls) == 1
        assert progress_calls[0] == (1, 1, "https://example.com/1")

    async def test_ingest_scrape_processes_single_page(self):
        ingestor = self._make_ingestor()
        insight = Insight(text="t", normalized_text="n", frame=Frame.CAUSAL, confidence=0.8)
        ingestor.normalizer.normalize = AsyncMock(return_value=[insight])
        ingestor.embeddings.embed_batch = MagicMock(
            return_value=np.zeros((1, 128), dtype=np.float32)
        )
        ingestor.crawl_service.scrape = AsyncMock(
            return_value=CrawledPage(url="https://example.com", markdown="## A\n\nContent")
        )

        count = await ingestor.ingest_scrape("kb-123", "https://example.com")
        assert count == 1
        ingestor.crawl_service.scrape.assert_called_once_with("https://example.com")

    async def test_ingest_page_handles_empty_markdown(self):
        ingestor = self._make_ingestor()
        page = CrawledPage(url="https://example.com", markdown="")
        count = await ingestor.ingest_page("kb-123", page)
        assert count == 0
        ingestor.normalizer.normalize.assert_not_called()

    async def test_ingest_page_uses_batch_embedding(self):
        """Verify embed_batch is used instead of per-insight embed."""
        ingestor = self._make_ingestor()
        insights = [
            Insight(text=f"t{i}", normalized_text=f"n{i}", frame=Frame.CAUSAL, entities=["x"], confidence=0.8)
            for i in range(5)
        ]
        ingestor.normalizer.normalize = AsyncMock(return_value=insights)
        ingestor.embeddings.embed_batch = MagicMock(
            return_value=np.random.rand(5, 128).astype(np.float32)
        )
        ingestor.embeddings.embed = MagicMock(side_effect=Exception("Should use batch"))

        page = CrawledPage(url="https://example.com", markdown="## Section\n\nSome content here.")
        count = await ingestor.ingest_page("kb-123", page)

        assert count == 5
        ingestor.embeddings.embed_batch.assert_called_once()
        assert len(ingestor.embeddings.embed_batch.call_args[0][0]) == 5

    async def test_ingest_page_filters_low_confidence(self):
        """Insights below MIN_CONFIDENCE_THRESHOLD are filtered out."""
        ingestor = self._make_ingestor()
        insights = [
            Insight(text="good", normalized_text="Good insight with detail", frame=Frame.CAUSAL, entities=["x"], confidence=0.8),
            Insight(text="bad", normalized_text="Bad", frame=Frame.TAXONOMY, confidence=0.2),
        ]
        ingestor.normalizer.normalize = AsyncMock(return_value=insights)
        ingestor.embeddings.embed_batch = MagicMock(
            return_value=np.random.rand(1, 128).astype(np.float32)
        )

        page = CrawledPage(url="https://example.com", markdown="## Section\n\nSome content here.")

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MIN_CONFIDENCE_THRESHOLD", "0.5")
            count = await ingestor.ingest_page("kb-123", page)

        assert count == 1
        ingestor.embeddings.embed_batch.assert_called_once()
        assert len(ingestor.embeddings.embed_batch.call_args[0][0]) == 1

    async def test_ingest_page_no_filtering_when_threshold_zero(self):
        """Setting MIN_CONFIDENCE_THRESHOLD=0.0 disables filtering."""
        ingestor = self._make_ingestor()
        insights = [
            Insight(text="low", normalized_text="X", frame=Frame.TAXONOMY, confidence=0.1),
            Insight(text="high", normalized_text="Y is good", frame=Frame.CAUSAL, entities=["Y"], confidence=0.9),
        ]
        ingestor.normalizer.normalize = AsyncMock(return_value=insights)
        ingestor.embeddings.embed_batch = MagicMock(
            return_value=np.random.rand(2, 128).astype(np.float32)
        )

        page = CrawledPage(url="https://example.com", markdown="## Section\n\nContent.")

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MIN_CONFIDENCE_THRESHOLD", "0.0")
            count = await ingestor.ingest_page("kb-123", page)

        assert count == 2
