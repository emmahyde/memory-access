from __future__ import annotations

import json
import os
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .crawl import CrawlService
from .embeddings import EmbeddingEngine, BedrockEmbeddingEngine
from .models import CrawledPage, KbChunk
from .normalizer import Normalizer
from .storage import InsightStore

logger = logging.getLogger(__name__)


def clean_markdown(text: str) -> str:
    """Strip common boilerplate from crawled markdown.

    Removes navigation headers (before first # heading) and
    feedback footers ("Did you find this page useful?" etc).
    """
    lines = text.split("\n")

    # Find first H1 heading — content starts there
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("# "):
            start = i
            break

    # Find footer markers — content ends before them
    end = len(lines)
    footer_markers = [
        "Did you find this page useful",
        "Thanks for rating this page",
        "Report a problem on this page",
    ]
    for i, line in enumerate(lines[start:], start):
        if any(marker in line for marker in footer_markers):
            end = i
            break

    return "\n".join(lines[start:end]).strip()


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
    """Orchestrates: crawl -> split -> normalize -> embed -> store."""

    def __init__(
        self,
        store: InsightStore,
        normalizer: Normalizer,
        embeddings: EmbeddingEngine | BedrockEmbeddingEngine,
        crawl_service: CrawlService | None = None,
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
        on_progress: Callable[..., Any] | None = None,
    ) -> int:
        """Crawl a URL and ingest all pages into a knowledge base.

        Returns the total number of chunks stored.
        """
        if self.crawl_service is None:
            raise RuntimeError("No crawl service configured")
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
        cleaned = clean_markdown(page.markdown)
        text_chunks = split_markdown(cleaned)

        # Collect all insights from all chunks
        all_insights = []
        for chunk_text in text_chunks:
            try:
                insights = await self.normalizer.normalize(chunk_text)
                all_insights.extend(insights)
            except Exception as e:
                logger.warning("Failed to normalize chunk from %s: %s", page.url, e)
                continue

        if not all_insights:
            return 0

        # Filter low-confidence insights
        min_threshold = float(os.environ.get("MIN_CONFIDENCE_THRESHOLD", "0.5"))
        filtered = [i for i in all_insights if i.confidence >= min_threshold]
        if len(all_insights) != len(filtered):
            logger.info(
                "Filtered %d/%d insights below confidence threshold %.2f",
                len(all_insights) - len(filtered), len(all_insights), min_threshold,
            )
        all_insights = filtered

        if not all_insights:
            return 0

        # Batch embed all normalized texts in single API call
        texts_to_embed = [i.normalized_text for i in all_insights]
        embeddings = self.embeddings.embed_batch(texts_to_embed)

        # Store with corresponding embeddings
        stored = 0
        for insight, emb in zip(all_insights, embeddings):
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
        if self.crawl_service is None:
            raise RuntimeError("No crawl service configured")
        page = await self.crawl_service.scrape(url)
        return await self.ingest_page(kb_id, page)

    async def ingest_from_directory(
        self,
        kb_id: str,
        dir_path: str,
        on_progress: Callable[..., Any] | None = None,
    ) -> int:
        """Load Firecrawl JSON files from a directory and ingest into a KB.

        Each JSON file should have {"markdown": "...", "metadata": {"sourceURL": "..."}}.
        Returns total chunks stored.
        """
        path = Path(dir_path)
        files = sorted(path.glob("*.json"))
        total_chunks = 0

        for i, f in enumerate(files):
            data = json.loads(f.read_text())
            markdown = data.get("markdown", "")
            metadata = data.get("metadata", {})
            url = metadata.get("sourceURL") or metadata.get("url", f.stem)

            if on_progress:
                on_progress(i + 1, len(files), url)

            page = CrawledPage(url=url, markdown=markdown, metadata=metadata)
            chunks_stored = await self.ingest_page(kb_id, page)
            total_chunks += chunks_stored

        return total_chunks
