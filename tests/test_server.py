import json
import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch
from memory_access.server import create_app
from memory_access.models import Frame


def _mock_anthropic_response(text: str):
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_response.content = [mock_content]
    return mock_response


def _mock_embedding_engine():
    """Create a mock EmbeddingEngine that returns deterministic vectors."""
    engine = MagicMock()
    call_count = [0]
    def _embed(text):
        call_count[0] += 1
        vec = np.zeros(128, dtype=np.float32)
        vec[call_count[0] % 128] = 1.0
        return vec
    engine.embed = _embed
    engine.embed_batch = lambda texts: np.array([_embed(t) for t in texts], dtype=np.float32)
    return engine


class TestStoreInsight:
    @pytest.mark.asyncio
    async def test_store_returns_confirmation(self, tmp_db):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(json.dumps(["Test insight"])),
            _mock_anthropic_response(json.dumps({
                "frame": "causal",
                "normalized": "Test causes effect",
                "entities": ["test"],
            })),
        ]
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.store_insight(text="Test insight", domain="testing", source="unit_test")
        result_data = json.loads(result)
        assert result_data["stored"] == 1
        assert len(result_data["ids"]) == 1

    @pytest.mark.asyncio
    async def test_store_compound_creates_multiple(self, tmp_db):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(json.dumps(["Insight A", "Insight B"])),
            _mock_anthropic_response(json.dumps({
                "frame": "causal",
                "normalized": "A causes B",
                "entities": ["A"],
            })),
            _mock_anthropic_response(json.dumps({
                "frame": "constraint",
                "normalized": "B requires C",
                "entities": ["B"],
            })),
        ]
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.store_insight(text="Insight A and Insight B", domain="", source="")
        result_data = json.loads(result)
        assert result_data["stored"] == 2
        assert len(result_data["ids"]) == 2


class TestSearchInsights:
    @pytest.mark.asyncio
    async def test_search_returns_ranked_results(self, tmp_db):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(json.dumps(["React re-renders on state change"])),
            _mock_anthropic_response(json.dumps({
                "frame": "causal",
                "normalized": "State change causes React re-render",
                "entities": ["React", "state"],
            })),
            _mock_anthropic_response(json.dumps(["Baking requires preheated oven"])),
            _mock_anthropic_response(json.dumps({
                "frame": "constraint",
                "normalized": "Baking requires preheated oven",
                "entities": ["baking", "oven"],
            })),
        ]
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        await app.store_insight(text="React re-renders on state change", domain="react")
        await app.store_insight(text="Baking requires preheated oven", domain="cooking")

        results = await app.search_insights(query="why does my React component re-render?", limit=2)
        results_data = json.loads(results)
        assert len(results_data) > 0
        assert results_data[0]["frame"] == "causal"
        assert "State change causes React re-render" in results_data[0]["text"]

    @pytest.mark.asyncio
    async def test_search_empty_returns_message(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.search_insights(query="anything")
        assert "No matching insights" in result


class TestUpdateInsight:
    @pytest.mark.asyncio
    async def test_update_existing_insight(self, tmp_db):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(json.dumps(["Initial insight"])),
            _mock_anthropic_response(json.dumps({
                "frame": "causal",
                "normalized": "A causes B",
                "entities": ["A"],
            })),
        ]
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        store_result = await app.store_insight(text="Initial insight")
        result_data = json.loads(store_result)
        insight_id = result_data["ids"][0]

        result = await app.update_insight(insight_id=insight_id, confidence=0.5)
        assert "Updated" in result

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.update_insight(insight_id="fake-id")
        assert "not found" in result.lower()


class TestForget:
    @pytest.mark.asyncio
    async def test_forget_existing(self, tmp_db):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(json.dumps(["Forget me"])),
            _mock_anthropic_response(json.dumps({
                "frame": "causal",
                "normalized": "Forget causes nothing",
                "entities": [],
            })),
        ]
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        store_result = await app.store_insight(text="Forget me")
        result_data = json.loads(store_result)
        insight_id = result_data["ids"][0]

        result = await app.forget(insight_id=insight_id)
        assert "Deleted" in result or "Forgot" in result

    @pytest.mark.asyncio
    async def test_forget_nonexistent(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.forget(insight_id="fake-id")
        assert "not found" in result.lower()


class TestListInsights:
    @pytest.mark.asyncio
    async def test_list_by_domain(self, tmp_db):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(json.dumps(["React insight"])),
            _mock_anthropic_response(json.dumps({
                "frame": "causal", "normalized": "React thing", "entities": [],
            })),
            _mock_anthropic_response(json.dumps(["Python insight"])),
            _mock_anthropic_response(json.dumps({
                "frame": "pattern", "normalized": "Python thing", "entities": [],
            })),
        ]
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        await app.store_insight(text="React insight", domain="react")
        await app.store_insight(text="Python insight", domain="python")

        result = await app.list_insights(domain="react")
        result_data = json.loads(result)
        texts = [item["text"] for item in result_data]
        assert "React thing" in texts
        assert "Python thing" not in texts

    @pytest.mark.asyncio
    async def test_list_by_frame(self, tmp_db):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(json.dumps(["Causal insight"])),
            _mock_anthropic_response(json.dumps({
                "frame": "causal", "normalized": "A causes B", "entities": [],
            })),
            _mock_anthropic_response(json.dumps(["Constraint insight"])),
            _mock_anthropic_response(json.dumps({
                "frame": "constraint", "normalized": "C requires D", "entities": [],
            })),
        ]
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        await app.store_insight(text="Causal insight")
        await app.store_insight(text="Constraint insight")

        result = await app.list_insights(frame="causal")
        result_data = json.loads(result)
        texts = [item["text"] for item in result_data]
        assert "A causes B" in texts
        assert "C requires D" not in texts


class TestSearchBySubject:
    @pytest.mark.asyncio
    async def test_search_by_subject_returns_matching(self, tmp_db):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _mock_anthropic_response(json.dumps(["Docker insight"])),
            _mock_anthropic_response(json.dumps({
                "frame": "pattern", "normalized": "Docker pattern", "entities": ["Docker"],
            })),
            _mock_anthropic_response(json.dumps(["Python insight"])),
            _mock_anthropic_response(json.dumps({
                "frame": "causal", "normalized": "Python causes X", "entities": ["Python"],
            })),
        ]
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        await app.store_insight(text="Docker insight", domain="devops")
        await app.store_insight(text="Python insight", domain="python")

        result = await app.search_by_subject(name="devops")
        result_data = json.loads(result)
        texts = [item["text"] for item in result_data]
        assert "Docker pattern" in texts
        assert not any("Python" in text for text in texts)

    @pytest.mark.asyncio
    async def test_search_by_subject_empty(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.search_by_subject(name="nonexistent")
        assert "No insights found" in result


class TestAddKnowledgeBase:
    @pytest.mark.asyncio
    async def test_add_kb_crawl(self, tmp_db):
        """Test creating a KB by crawling."""
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())

        # Mock the crawl service
        with patch("memory_access.crawl.create_crawl_service") as mock_crawl_factory:
            mock_crawl = AsyncMock()
            mock_crawl_factory.return_value = mock_crawl

            # Mock crawl to return a page
            from memory_access.models import CrawledPage
            mock_crawl.crawl.return_value = [
                CrawledPage(
                    url="https://example.com/page1",
                    markdown="# Example\n\nThis is test content.",
                    metadata={},
                )
            ]

            # Mock normalizer
            with patch.object(app.normalizer, "normalize") as mock_normalize:
                from memory_access.models import Insight
                mock_normalize.return_value = [
                    Insight(
                        text="This is test content.",
                        normalized_text="This is test content.",
                        frame=Frame.CAUSAL,
                        domains=["test"],
                        entities=[],
                        problems=[],
                        resolutions=[],
                        contexts=[],
                        confidence=0.8,
                    )
                ]

                result = await app.add_knowledge_base(
                    name="test-kb",
                    url="https://example.com",
                    description="Test KB",
                    scrape_only=False,
                    limit=1000,
                )

                assert "✓ Created KB 'test-kb'" in result
                assert "chunks" in result

                # Verify KB was created
                kb = await app.store.get_kb_by_name("test-kb")
                assert kb is not None
                assert kb.name == "test-kb"
                assert kb.description == "Test KB"

    @pytest.mark.asyncio
    async def test_add_kb_scrape_only(self, tmp_db):
        """Test creating a KB by scraping a single URL."""
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())

        with patch("memory_access.crawl.create_crawl_service") as mock_crawl_factory:
            mock_crawl = AsyncMock()
            mock_crawl_factory.return_value = mock_crawl

            from memory_access.models import CrawledPage
            mock_crawl.scrape.return_value = CrawledPage(
                url="https://example.com",
                markdown="# Single Page\n\nContent here.",
                metadata={},
            )

            with patch.object(app.normalizer, "normalize") as mock_normalize:
                from memory_access.models import Insight
                mock_normalize.return_value = [
                    Insight(
                        text="Content here.",
                        normalized_text="Content here.",
                        frame=Frame.PATTERN,
                        domains=["web"],
                        entities=[],
                        problems=[],
                        resolutions=[],
                        contexts=[],
                        confidence=0.75,
                    )
                ]

                result = await app.add_knowledge_base(
                    name="single-page-kb",
                    url="https://example.com",
                    description="Single page KB",
                    scrape_only=True,
                )

                assert "✓ Created KB 'single-page-kb'" in result
                assert "from https://example.com" in result

    @pytest.mark.asyncio
    async def test_add_kb_already_exists(self, tmp_db):
        """Test that creating a KB with duplicate name fails gracefully."""
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())

        # Create first KB
        await app.store.create_kb("duplicate-kb", description="First")

        # Try to create with same name
        result = await app.add_knowledge_base(
            name="duplicate-kb",
            url="https://example.com",
            description="Second",
        )

        assert "already exists" in result.lower()

    @pytest.mark.asyncio
    async def test_add_kb_ingest_failure_cleanup(self, tmp_db):
        """Test that KB is cleaned up if ingestion fails."""
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())

        with patch("memory_access.crawl.create_crawl_service") as mock_crawl_factory:
            mock_crawl = AsyncMock()
            mock_crawl_factory.return_value = mock_crawl
            mock_crawl.crawl.side_effect = Exception("Crawl failed")

            result = await app.add_knowledge_base(
                name="failed-kb",
                url="https://example.com",
                description="Will fail",
            )

            assert "✗ Failed to ingest KB" in result
            assert "Crawl failed" in result

            # Verify KB was cleaned up
            kb = await app.store.get_kb_by_name("failed-kb")
            assert kb is None


class TestSearchKnowledgeBase:
    @pytest.mark.asyncio
    async def test_search_kb_returns_results(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        # Create a KB and insert a chunk with embedding
        kb_id = await app.store.create_kb("test-kb", description="Test KB")
        from memory_access.models import KbChunk
        emb = np.array([1.0, 0.0, 0.0] + [0.0] * 125, dtype=np.float32)
        chunk = KbChunk(
            kb_id=kb_id, text="Rails uses MVC", normalized_text="Rails framework uses MVC pattern",
            frame=Frame.PATTERN, domains=["rails"],
        )
        await app.store.insert_kb_chunk(chunk, embedding=emb)

        result = await app.search_knowledge_base(query="How does Rails work?", limit=5)
        result_data = json.loads(result)
        texts = [item["text"] for item in result_data]
        assert "Rails framework uses MVC pattern" in texts

    @pytest.mark.asyncio
    async def test_search_kb_by_name(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        kb_id = await app.store.create_kb("rails-docs")
        from memory_access.models import KbChunk
        emb = np.array([1.0, 0.0, 0.0] + [0.0] * 125, dtype=np.float32)
        await app.store.insert_kb_chunk(
            KbChunk(kb_id=kb_id, text="t", normalized_text="Rails content", frame=Frame.CAUSAL),
            embedding=emb,
        )

        result = await app.search_knowledge_base(query="rails", kb_name="rails-docs")
        result_data = json.loads(result)
        texts = [item["text"] for item in result_data]
        assert "Rails content" in texts

    @pytest.mark.asyncio
    async def test_search_kb_not_found(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.search_knowledge_base(query="anything", kb_name="nonexistent")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_search_kb_empty(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.search_knowledge_base(query="anything")
        assert "No matching content" in result


class TestListKnowledgeBases:
    @pytest.mark.asyncio
    async def test_list_kbs_returns_formatted(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        await app.store.create_kb("rails-docs", description="Rails documentation", source_type="crawl")
        await app.store.create_kb("python-docs", description="Python docs", source_type="scrape")

        result = await app.list_knowledge_bases()
        result_data = json.loads(result)
        names = [item["name"] for item in result_data]
        descriptions = [item.get("description") for item in result_data]
        assert "rails-docs" in names
        assert "python-docs" in names
        assert "Rails documentation" in descriptions

    @pytest.mark.asyncio
    async def test_list_kbs_empty(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.list_knowledge_bases()
        assert "No knowledge bases" in result
