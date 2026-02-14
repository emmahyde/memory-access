import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from memory_access.crawl import create_crawl_service, FirecrawlService, CrawlService
from memory_access.models import CrawledPage


class TestCreateCrawlService:
    def test_default_returns_firecrawl(self):
        with patch.dict("os.environ", {"FIRECRAWL_API_KEY": "test-key"}):
            with patch("firecrawl.FirecrawlApp"):
                service = create_crawl_service()
                assert isinstance(service, FirecrawlService)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown crawl service"):
            create_crawl_service(provider="unknown")

    def test_env_var_selects_provider(self):
        with patch.dict(
            "os.environ", {"CRAWL_SERVICE": "firecrawl", "FIRECRAWL_API_KEY": "test"}
        ):
            with patch("firecrawl.FirecrawlApp"):
                service = create_crawl_service()
                assert isinstance(service, FirecrawlService)

    def test_explicit_provider_parameter(self):
        with patch("firecrawl.FirecrawlApp"):
            service = create_crawl_service(provider="firecrawl", api_key="test-key")
            assert isinstance(service, FirecrawlService)


class TestFirecrawlServiceCrawl:
    async def test_crawl_returns_pages(self):
        # Mock CrawlJob and Document
        mock_metadata = MagicMock()
        mock_metadata.url = "https://example.com/page1"
        mock_metadata.source_url = None
        mock_metadata.model_dump = MagicMock(return_value={"url": "https://example.com/page1"})

        mock_doc1 = MagicMock()
        mock_doc1.markdown = "# Page 1"
        mock_doc1.metadata = mock_metadata

        mock_metadata2 = MagicMock()
        mock_metadata2.url = "https://example.com/page2"
        mock_metadata2.source_url = None
        mock_metadata2.model_dump = MagicMock(return_value={"url": "https://example.com/page2"})

        mock_doc2 = MagicMock()
        mock_doc2.markdown = "# Page 2"
        mock_doc2.metadata = mock_metadata2

        mock_crawl_job = MagicMock()
        mock_crawl_job.data = [mock_doc1, mock_doc2]

        with patch("firecrawl.FirecrawlApp") as MockFirecrawlApp:
            mock_app = MagicMock()
            mock_app.crawl = MagicMock(return_value=mock_crawl_job)
            MockFirecrawlApp.return_value = mock_app

            service = FirecrawlService(api_key="test-key")
            pages = await service.crawl("https://example.com", limit=10)

            assert len(pages) == 2
            assert pages[0].url == "https://example.com/page1"
            assert pages[0].markdown == "# Page 1"
            assert pages[1].url == "https://example.com/page2"
            assert pages[1].markdown == "# Page 2"

            call_args = mock_app.crawl.call_args
            assert call_args.args[0] == "https://example.com"
            assert call_args.kwargs["limit"] == 10
            opts = call_args.kwargs["scrape_options"]
            assert opts.formats == ["markdown"]
            assert opts.only_main_content is True

    async def test_crawl_handles_missing_metadata(self):
        # Test when metadata is None
        mock_doc = MagicMock()
        mock_doc.markdown = "# Content"
        mock_doc.metadata = None

        mock_crawl_job = MagicMock()
        mock_crawl_job.data = [mock_doc]

        with patch("firecrawl.FirecrawlApp") as MockFirecrawlApp:
            mock_app = MagicMock()
            mock_app.crawl = MagicMock(return_value=mock_crawl_job)
            MockFirecrawlApp.return_value = mock_app

            service = FirecrawlService(api_key="test-key")
            pages = await service.crawl("https://example.com")

            assert len(pages) == 1
            assert pages[0].url == "https://example.com"
            assert pages[0].markdown == "# Content"
            assert pages[0].metadata == {}

    async def test_crawl_uses_source_url_fallback(self):
        # Test when url is None but source_url is available
        mock_metadata = MagicMock()
        mock_metadata.url = None
        mock_metadata.source_url = "https://example.com/source"
        mock_metadata.model_dump = MagicMock(
            return_value={"source_url": "https://example.com/source"}
        )

        mock_doc = MagicMock()
        mock_doc.markdown = "# Content"
        mock_doc.metadata = mock_metadata

        mock_crawl_job = MagicMock()
        mock_crawl_job.data = [mock_doc]

        with patch("firecrawl.FirecrawlApp") as MockFirecrawlApp:
            mock_app = MagicMock()
            mock_app.crawl = MagicMock(return_value=mock_crawl_job)
            MockFirecrawlApp.return_value = mock_app

            service = FirecrawlService(api_key="test-key")
            pages = await service.crawl("https://example.com")

            assert len(pages) == 1
            assert pages[0].url == "https://example.com/source"


class TestFirecrawlServiceScrape:
    async def test_scrape_returns_page(self):
        mock_metadata = MagicMock()
        mock_metadata.url = "https://example.com/page"
        mock_metadata.source_url = None
        mock_metadata.model_dump = MagicMock(return_value={"url": "https://example.com/page"})

        mock_doc = MagicMock()
        mock_doc.markdown = "# Test Page"
        mock_doc.metadata = mock_metadata

        with patch("firecrawl.FirecrawlApp") as MockFirecrawlApp:
            mock_app = MagicMock()
            mock_app.scrape = MagicMock(return_value=mock_doc)
            MockFirecrawlApp.return_value = mock_app

            service = FirecrawlService(api_key="test-key")
            page = await service.scrape("https://example.com")

            assert page.url == "https://example.com/page"
            assert page.markdown == "# Test Page"

            mock_app.scrape.assert_called_once_with(
                "https://example.com",
                formats=["markdown"],
                only_main_content=True,
            )

    async def test_scrape_handles_missing_metadata(self):
        mock_doc = MagicMock()
        mock_doc.markdown = "# Content"
        mock_doc.metadata = None

        with patch("firecrawl.FirecrawlApp") as MockFirecrawlApp:
            mock_app = MagicMock()
            mock_app.scrape = MagicMock(return_value=mock_doc)
            MockFirecrawlApp.return_value = mock_app

            service = FirecrawlService(api_key="test-key")
            page = await service.scrape("https://example.com")

            assert page.url == "https://example.com"
            assert page.markdown == "# Content"
            assert page.metadata == {}

    async def test_scrape_uses_source_url_fallback(self):
        mock_metadata = MagicMock()
        mock_metadata.url = None
        mock_metadata.source_url = "https://example.com/source"
        mock_metadata.model_dump = MagicMock(
            return_value={"source_url": "https://example.com/source"}
        )

        mock_doc = MagicMock()
        mock_doc.markdown = "# Content"
        mock_doc.metadata = mock_metadata

        with patch("firecrawl.FirecrawlApp") as MockFirecrawlApp:
            mock_app = MagicMock()
            mock_app.scrape = MagicMock(return_value=mock_doc)
            MockFirecrawlApp.return_value = mock_app

            service = FirecrawlService(api_key="test-key")
            page = await service.scrape("https://example.com")

            assert page.url == "https://example.com/source"


class TestFirecrawlServiceInit:
    def test_init_with_api_key(self):
        with patch("firecrawl.FirecrawlApp") as MockFirecrawlApp:
            service = FirecrawlService(api_key="explicit-key")
            MockFirecrawlApp.assert_called_once_with(api_key="explicit-key")

    def test_init_with_env_var(self):
        with patch.dict("os.environ", {"FIRECRAWL_API_KEY": "env-key"}):
            with patch("firecrawl.FirecrawlApp") as MockFirecrawlApp:
                service = FirecrawlService()
                MockFirecrawlApp.assert_called_once_with(api_key="env-key")

    def test_init_without_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("firecrawl.FirecrawlApp") as MockFirecrawlApp:
                service = FirecrawlService()
                MockFirecrawlApp.assert_called_once_with(api_key="")
