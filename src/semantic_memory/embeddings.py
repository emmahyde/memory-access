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
