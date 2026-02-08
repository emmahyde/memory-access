import json

import numpy as np
from unittest.mock import MagicMock, patch
from memory_access.embeddings import EmbeddingEngine, BedrockEmbeddingEngine, create_embedding_engine


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



def _mock_bedrock_response(embedding: list[float]):
    """Create a mock Bedrock invoke_model response."""
    body = MagicMock()
    body.read.return_value = json.dumps({"embedding": embedding}).encode()
    return {"body": body}


class TestBedrockEmbeddingEngine:
    def test_embed_returns_float32_array(self):
        engine = BedrockEmbeddingEngine()
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = _mock_bedrock_response(
            [0.1, 0.2, 0.3, 0.4]
        )
        engine._client = mock_client

        result = engine.embed("hello world")
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float32
        assert result.shape == (4,)

    def test_embed_is_normalized(self):
        engine = BedrockEmbeddingEngine()
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = _mock_bedrock_response([3.0, 4.0])
        engine._client = mock_client

        result = engine.embed("test sentence")
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-5

    def test_embed_batch(self):
        engine = BedrockEmbeddingEngine()
        mock_client = MagicMock()
        mock_client.invoke_model.side_effect = [
            _mock_bedrock_response([1.0, 0.0]),
            _mock_bedrock_response([0.0, 1.0]),
            _mock_bedrock_response([1.0, 1.0]),
        ]
        engine._client = mock_client

        results = engine.embed_batch(["hello", "world", "test"])
        assert results.shape == (3, 2)
        assert results.dtype == np.float32
        for row in results:
            assert abs(np.linalg.norm(row) - 1.0) < 1e-5

    def test_invoke_model_called_with_correct_params(self):
        engine = BedrockEmbeddingEngine(model="amazon.titan-embed-text-v2:0")
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = _mock_bedrock_response([0.5, 0.5])
        engine._client = mock_client

        engine.embed("test")
        mock_client.invoke_model.assert_called_once_with(
            modelId="amazon.titan-embed-text-v2:0",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({"inputText": "test"}),
        )

    def test_default_model_from_env(self):
        with patch.dict("os.environ", {"BEDROCK_EMBEDDING_MODEL": "custom-model"}):
            engine = BedrockEmbeddingEngine()
            assert engine._model == "custom-model"

    def test_default_region_from_env(self):
        with patch.dict("os.environ", {"AWS_REGION": "eu-west-1"}):
            engine = BedrockEmbeddingEngine()
            assert engine._aws_region == "eu-west-1"


class TestCreateEmbeddingEngine:
    def test_default_returns_openai(self):
        engine = create_embedding_engine()
        assert isinstance(engine, EmbeddingEngine)

    def test_bedrock_returns_bedrock(self):
        engine = create_embedding_engine(provider="bedrock")
        assert isinstance(engine, BedrockEmbeddingEngine)

    def test_env_var_selects_provider(self):
        with patch.dict("os.environ", {"EMBEDDING_PROVIDER": "bedrock"}):
            engine = create_embedding_engine()
            assert isinstance(engine, BedrockEmbeddingEngine)

    def test_explicit_provider_overrides_env(self):
        with patch.dict("os.environ", {"EMBEDDING_PROVIDER": "bedrock"}):
            engine = create_embedding_engine(provider="openai")
            assert isinstance(engine, EmbeddingEngine)
