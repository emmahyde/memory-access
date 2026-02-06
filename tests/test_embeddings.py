import numpy as np
from semantic_memory.embeddings import EmbeddingEngine


class TestEmbeddingEngine:
    def test_embed_returns_float32_array(self):
        engine = EmbeddingEngine()
        result = engine.embed("hello world")
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert len(result.shape) == 1
        assert result.shape[0] > 0

    def test_embed_is_normalized(self):
        engine = EmbeddingEngine()
        result = engine.embed("test sentence")
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-5

    def test_similar_texts_have_high_similarity(self):
        engine = EmbeddingEngine()
        a = engine.embed("React re-renders when state changes")
        b = engine.embed("State mutations trigger React re-render cycles")
        c = engine.embed("How to bake a chocolate cake")
        sim_ab = float(np.dot(a, b))
        sim_ac = float(np.dot(a, c))
        assert sim_ab > sim_ac, "Similar texts should have higher cosine similarity"
        assert sim_ab > 0.5

    def test_embed_batch(self):
        engine = EmbeddingEngine()
        texts = ["hello", "world", "test"]
        results = engine.embed_batch(texts)
        assert results.shape[0] == 3
        assert results.dtype == np.float32
