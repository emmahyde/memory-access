import pytest
import numpy as np
from semantic_memory.storage import InsightStore
from semantic_memory.models import Frame, Insight


class TestInsightStoreInit:
    async def test_initialize_creates_tables(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        # Verify table exists by inserting
        insight = Insight(
            text="test insight",
            normalized_text="test insight normalized",
            frame=Frame.CAUSAL,
        )
        insight_id = await store.insert(insight)
        assert isinstance(insight_id, str)
        assert len(insight_id) == 36  # UUID length


class TestInsightStoreInsert:
    async def test_insert_minimal_insight(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(text="test", normalized_text="test", frame=Frame.CAUSAL)
        insight_id = await store.insert(insight)
        assert insight_id is not None

    async def test_insert_with_embedding(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(text="test", normalized_text="test", frame=Frame.CAUSAL)
        embedding = np.random.randn(384).astype(np.float32)
        insight_id = await store.insert(insight, embedding=embedding)
        assert insight_id is not None

    async def test_insert_preserves_all_fields(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(
            text="original text",
            normalized_text="state mutation causes re-render skip",
            frame=Frame.CAUSAL,
            domains=["react", "frontend"],
            entities=["React", "state"],
            confidence=0.9,
            source="debug_session",
        )
        insight_id = await store.insert(insight)
        retrieved = await store.get(insight_id)
        assert retrieved is not None
        assert retrieved.text == "original text"
        assert retrieved.normalized_text == "state mutation causes re-render skip"
        assert retrieved.frame == Frame.CAUSAL
        assert retrieved.domains == ["react", "frontend"]
        assert retrieved.entities == ["React", "state"]
        assert retrieved.confidence == 0.9
        assert retrieved.source == "debug_session"


class TestInsightStoreUpdate:
    async def test_update_text_fields(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(text="old", normalized_text="old", frame=Frame.CAUSAL)
        iid = await store.insert(insight)
        updated = await store.update(iid, normalized_text="new", confidence=0.5)
        assert updated is not None
        assert updated.normalized_text == "new"
        assert updated.confidence == 0.5
        assert updated.text == "old"  # unchanged

    async def test_update_nonexistent_returns_none(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        result = await store.update("nonexistent-id", confidence=0.1)
        assert result is None


class TestInsightStoreDelete:
    async def test_delete_existing(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        insight = Insight(text="delete me", normalized_text="delete me", frame=Frame.CAUSAL)
        iid = await store.insert(insight)
        deleted = await store.delete(iid)
        assert deleted is True
        assert await store.get(iid) is None

    async def test_delete_nonexistent(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        deleted = await store.delete("nonexistent-id")
        assert deleted is False


class TestInsightStoreSearch:
    async def test_search_by_embedding_returns_ranked(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        # Create two insights with known embeddings
        emb_a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        emb_b = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        await store.insert(
            Insight(text="a", normalized_text="a", frame=Frame.CAUSAL), embedding=emb_a
        )
        await store.insert(
            Insight(text="b", normalized_text="b", frame=Frame.CAUSAL), embedding=emb_b
        )

        # Query closer to emb_a
        query = np.array([0.9, 0.1, 0.0], dtype=np.float32)
        results = await store.search_by_embedding(query, limit=2)

        assert len(results) == 2
        assert results[0].insight.text == "a"
        assert results[0].score > results[1].score

    async def test_search_with_domain_filter(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()

        emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        await store.insert(
            Insight(text="react thing", normalized_text="r", frame=Frame.CAUSAL, domains=["react"]),
            embedding=emb,
        )
        await store.insert(
            Insight(text="python thing", normalized_text="p", frame=Frame.CAUSAL, domains=["python"]),
            embedding=emb,
        )

        results = await store.search_by_embedding(emb, limit=10, domain="react")
        assert len(results) == 1
        assert results[0].insight.text == "react thing"

    async def test_search_empty_db(self, tmp_db):
        store = InsightStore(tmp_db)
        await store.initialize()
        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = await store.search_by_embedding(query)
        assert results == []
