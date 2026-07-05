from __future__ import annotations

import hashlib

import numpy as np


class EmbeddingModel:
    def __init__(self, model_name: str) -> None:
        self.model = None
        self.dimension = 384
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(model_name)
        except Exception:
            self.model = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self.model is None:
            return [self._fallback_embedding(text) for text in texts]

        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype="float32").tolist()

    def _fallback_embedding(self, text: str) -> list[float]:
        vector = np.zeros(self.dimension, dtype="float32")
        words = text.lower().split()
        tokens = words + [text.lower()[idx : idx + 4] for idx in range(max(len(text) - 3, 0))]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += 1.0
        norm = float(np.linalg.norm(vector))
        if norm:
            vector = vector / norm
        return vector.tolist()
