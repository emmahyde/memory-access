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

        resolved_key = api_key or os.environ.get("FIRECRAWL_API_KEY", "")
        self.app = FirecrawlApp(api_key=resolved_key)

    async def crawl(self, url: str, limit: int = 1000) -> list[CrawledPage]:
        """Crawl a URL using Firecrawl. Returns markdown pages."""
        from firecrawl.v2.types import ScrapeOptions

        result = self.app.crawl(
            url,
            limit=limit,
            scrape_options=ScrapeOptions(formats=["markdown"], only_main_content=True),
        )

        pages = []
        for doc in result.data:
            # Extract URL from metadata, fallback to base URL
            page_url = url
            if doc.metadata and doc.metadata.url:
                page_url = doc.metadata.url
            elif doc.metadata and doc.metadata.source_url:
                page_url = doc.metadata.source_url

            pages.append(
                CrawledPage(
                    url=page_url,
                    markdown=doc.markdown or "",
                    metadata=doc.metadata.model_dump(exclude_none=True) if doc.metadata else {},
                )
            )
        return pages

    async def scrape(self, url: str) -> CrawledPage:
        """Scrape a single URL using Firecrawl."""
        result = self.app.scrape(
            url,
            formats=["markdown"],
            only_main_content=True,
        )

        # Extract URL from metadata, fallback to input URL
        page_url = url
        if result.metadata and result.metadata.url:
            page_url = result.metadata.url
        elif result.metadata and result.metadata.source_url:
            page_url = result.metadata.source_url

        return CrawledPage(
            url=page_url,
            markdown=result.markdown or "",
            metadata=result.metadata.model_dump(exclude_none=True) if result.metadata else {},
        )


def create_crawl_service(provider: str | None = None, **kwargs) -> CrawlService:
    """Factory to create the appropriate crawl service."""
    provider = provider or os.environ.get("CRAWL_SERVICE", "firecrawl")
    if provider == "firecrawl":
        return FirecrawlService(**kwargs)
    raise ValueError(f"Unknown crawl service: {provider}")
