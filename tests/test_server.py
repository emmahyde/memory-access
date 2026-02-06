import json
import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch
from sem_mem.server import create_app
from sem_mem.models import Frame


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
        assert "Stored 1 insight" in result

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
        assert "Stored 2 insight" in result


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
        assert "State change causes React re-render" in results
        lines = results.strip().split("\n")
        assert "causal" in lines[0].lower()

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
        insight_id = store_result.split(": ")[1].strip()

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
        insight_id = store_result.split(": ")[1].strip()

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
        assert "React thing" in result
        assert "Python thing" not in result

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
        assert "A causes B" in result
        assert "C requires D" not in result


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
        assert "Docker pattern" in result
        assert "Python" not in result

    @pytest.mark.asyncio
    async def test_search_by_subject_empty(self, tmp_db):
        mock_client = MagicMock()
        app = await create_app(db_path=tmp_db, anthropic_client=mock_client, embeddings=_mock_embedding_engine())
        result = await app.search_by_subject(name="nonexistent")
        assert "No insights found" in result
