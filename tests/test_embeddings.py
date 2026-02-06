import numpy as np
from unittest.mock import MagicMock, patch
from semantic_memory.embeddings import EmbeddingEngine


def _mock_embedding_response(embeddings: list[list[float]]):
    """Create a mock OpenAI embeddings response."""
    mock_response = MagicMock()
    mock_response.data = []
    for emb in embeddings:
        mock_datum = MagicMock()
        mock_datum.embedding = emb
        mock_response.data.append(mock_datum)
    return mock_response


class TestEmbeddingEngine:
    def test_embed_returns_float32_array(self):
        engine = EmbeddingEngine()
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = _mock_embedding_response(
            [[0.1, 0.2, 0.3, 0.4]]
        )
        engine._client = mock_client

        result = engine.embed("hello world")
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert len(result.shape) == 1
        assert result.shape[0] == 4

    def test_embed_is_normalized(self):
        engine = EmbeddingEngine()
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = _mock_embedding_response(
            [[3.0, 4.0]]
        )
        engine._client = mock_client

        result = engine.embed("test sentence")
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-5

    def test_embed_batch(self):
        engine = EmbeddingEngine()
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = _mock_embedding_response(
            [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
        )
        engine._client = mock_client

        results = engine.embed_batch(["hello", "world", "test"])
        assert results.shape == (3, 2)
        assert results.dtype == np.float32
        # Each row should be normalized
        for row in results:
            assert abs(np.linalg.norm(row) - 1.0) < 1e-5

    def test_embed_calls_correct_model(self):
        engine = EmbeddingEngine(model="text-embedding-3-small")
        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = _mock_embedding_response(
            [[0.5, 0.5]]
        )
        engine._client = mock_client

        engine.embed("test")
        mock_client.embeddings.create.assert_called_once_with(
            input=["test"], model="text-embedding-3-small"
        )
