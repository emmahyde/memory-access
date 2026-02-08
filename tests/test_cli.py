import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from sem_mem.cli import _dispatch, _cmd_new, _cmd_list, _cmd_delete, _cmd_refresh


class TestCmdList:
    async def test_list_empty(self, tmp_db, capsys):
        from sem_mem.server import create_app
        app = await create_app(db_path=tmp_db, anthropic_client=MagicMock(), embeddings=MagicMock())
        await _cmd_list(app)
        captured = capsys.readouterr()
        assert "No knowledge bases" in captured.err

    async def test_list_with_kbs(self, tmp_db, capsys):
        from sem_mem.server import create_app
        app = await create_app(db_path=tmp_db, anthropic_client=MagicMock(), embeddings=MagicMock())
        await app.store.create_kb("rails-docs", description="Rails documentation", source_type="crawl")
        await _cmd_list(app)
        captured = capsys.readouterr()
        assert "rails-docs" in captured.err
        assert "Rails documentation" in captured.err


class TestCmdDelete:
    async def test_delete_existing(self, tmp_db, capsys):
        from sem_mem.server import create_app
        app = await create_app(db_path=tmp_db, anthropic_client=MagicMock(), embeddings=MagicMock())
        await app.store.create_kb("to-delete")
        args = MagicMock()
        args.name = "to-delete"
        await _cmd_delete(app, args)
        captured = capsys.readouterr()
        assert "Deleted" in captured.err

    async def test_delete_nonexistent(self, tmp_db, capsys):
        from sem_mem.server import create_app
        app = await create_app(db_path=tmp_db, anthropic_client=MagicMock(), embeddings=MagicMock())
        args = MagicMock()
        args.name = "nonexistent"
        await _cmd_delete(app, args)
        captured = capsys.readouterr()
        assert "not found" in captured.err


class TestCmdNew:
    async def test_new_without_source(self, tmp_db, capsys):
        from sem_mem.server import create_app
        app = await create_app(db_path=tmp_db, anthropic_client=MagicMock(), embeddings=MagicMock())
        ingestor = MagicMock()
        args = MagicMock()
        args.name = "my-kb"
        args.description = "Test KB"
        args.crawl = None
        args.scrape = None
        args.from_dir = None
        args.limit = 1000
        await _cmd_new(app, ingestor, args)
        captured = capsys.readouterr()
        assert "Created knowledge base" in captured.err
        assert "my-kb" in captured.err

    async def test_new_with_crawl(self, tmp_db, capsys):
        from sem_mem.server import create_app
        app = await create_app(db_path=tmp_db, anthropic_client=MagicMock(), embeddings=MagicMock())
        ingestor = MagicMock()
        ingestor.ingest_crawl = AsyncMock(return_value=42)
        args = MagicMock()
        args.name = "crawled-kb"
        args.description = ""
        args.crawl = "https://example.com"
        args.scrape = None
        args.limit = 10
        await _cmd_new(app, ingestor, args)
        captured = capsys.readouterr()
        assert "Ingested 42 chunks" in captured.err
        ingestor.ingest_crawl.assert_called_once()

    async def test_new_with_scrape(self, tmp_db, capsys):
        from sem_mem.server import create_app
        app = await create_app(db_path=tmp_db, anthropic_client=MagicMock(), embeddings=MagicMock())
        ingestor = MagicMock()
        ingestor.ingest_scrape = AsyncMock(return_value=5)
        args = MagicMock()
        args.name = "scraped-kb"
        args.description = ""
        args.crawl = None
        args.scrape = "https://example.com/page"
        args.limit = 1000
        await _cmd_new(app, ingestor, args)
        captured = capsys.readouterr()
        assert "Ingested 5 chunks" in captured.err
        ingestor.ingest_scrape.assert_called_once()


class TestCmdRefresh:
    async def test_refresh_nonexistent(self, tmp_db, capsys):
        from sem_mem.server import create_app
        app = await create_app(db_path=tmp_db, anthropic_client=MagicMock(), embeddings=MagicMock())
        ingestor = MagicMock()
        args = MagicMock()
        args.name = "nonexistent"
        await _cmd_refresh(app, ingestor, args)
        captured = capsys.readouterr()
        assert "not found" in captured.err

    async def test_refresh_clears_chunks(self, tmp_db, capsys):
        from sem_mem.server import create_app
        from sem_mem.models import KbChunk, Frame
        app = await create_app(db_path=tmp_db, anthropic_client=MagicMock(), embeddings=MagicMock())
        kb_id = await app.store.create_kb("test-kb", source_type="crawl")
        await app.store.insert_kb_chunk(KbChunk(kb_id=kb_id, text="old", normalized_text="old", frame=Frame.CAUSAL))
        ingestor = MagicMock()
        args = MagicMock()
        args.name = "test-kb"
        args.limit = 100
        await _cmd_refresh(app, ingestor, args)
        captured = capsys.readouterr()
        assert "Deleted 1 existing chunks" in captured.err
