import json
import os

import numpy as np
import openai


class EmbeddingEngine:
    """Generates normalized embeddings using OpenAI's text-embedding-3-small model."""

    def __init__(self, model: str = "text-embedding-3-small"):
        self._client: openai.OpenAI | None = None
        self._model = model

    @property
    def client(self) -> openai.OpenAI:
        if self._client is None:
            self._client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        return self._client

    def embed(self, text: str) -> np.ndarray:
        response = self.client.embeddings.create(input=[text], model=self._model)
        vec = np.array(response.data[0].embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        response = self.client.embeddings.create(input=texts, model=self._model)
        vecs = np.array([d.embedding for d in response.data], dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return vecs / norms


class BedrockEmbeddingEngine:
    """Generates normalized embeddings using Amazon Titan via AWS Bedrock."""

    def __init__(
        self,
        model: str | None = None,
        aws_region: str | None = None,
        aws_profile: str | None = None,
    ):
        self._client = None
        self._model = model or os.environ.get(
            "BEDROCK_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0"
        )
        self._aws_region = aws_region or os.environ.get("AWS_REGION", "us-east-1")
        self._aws_profile = aws_profile or os.environ.get("AWS_PROFILE")

    @property
    def client(self):
        if self._client is None:
            import boto3

            session = boto3.Session(
                region_name=self._aws_region,
                profile_name=self._aws_profile,
            )
            self._client = session.client("bedrock-runtime")
        return self._client

    def _invoke(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text})
        response = self.client.invoke_model(
            modelId=self._model,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        result = json.loads(response["body"].read())
        return result["embedding"]

    def embed(self, text: str) -> np.ndarray:
        vec = np.array(self._invoke(text), dtype=np.float32)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(self._invoke, texts))
        vecs = np.array(results, dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1
        return vecs / norms


def create_embedding_engine(
    provider: str | None = None, **kwargs
) -> EmbeddingEngine | BedrockEmbeddingEngine:
    """Factory to create the appropriate embedding engine based on provider."""
    provider = provider or os.environ.get("EMBEDDING_PROVIDER", "openai")
    if provider == "bedrock":
        return BedrockEmbeddingEngine(**kwargs)
    return EmbeddingEngine(**kwargs)
