import numpy as np
from sentence_transformers import SentenceTransformer


class EmbeddingEngine:
    """Generates normalized embeddings using a local sentence-transformers model."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model: SentenceTransformer | None = None
        self._model_name = model_name

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, text: str) -> np.ndarray:
        return self.model.encode(text, normalize_embeddings=True).astype(np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True).astype(np.float32)
