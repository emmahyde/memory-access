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
