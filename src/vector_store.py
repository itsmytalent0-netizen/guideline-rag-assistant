from __future__ import annotations

from collections.abc import Iterable

import chromadb

from src.embeddings import EmbeddingModel
from src.models import Document


class ChromaVectorStore:
    def __init__(self, persist_dir: str, embedding_model: EmbeddingModel) -> None:
        self.embedding_model = embedding_model
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="guideline_chunks",
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return self.collection.count()

    def upsert(self, documents: Iterable[Document]) -> None:
        docs = list(documents)
        if not docs:
            return
        embeddings = self.embedding_model.encode([doc.text for doc in docs])
        self.collection.upsert(
            ids=[doc.id for doc in docs],
            documents=[doc.text for doc in docs],
            embeddings=embeddings,
            metadatas=[doc.metadata for doc in docs],
        )

    def query(self, question: str, top_k: int) -> dict[str, float]:
        if self.count() == 0:
            return {}
        embedding = self.embedding_model.encode([question])[0]
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["distances"],
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        scores: dict[str, float] = {}
        for doc_id, distance in zip(ids, distances, strict=False):
            scores[doc_id] = max(0.0, 1.0 - float(distance))
        return scores

    def get_all(self) -> list[Document]:
        if self.count() == 0:
            return []
        result = self.collection.get(include=["documents", "metadatas"])
        docs = []
        for doc_id, text, metadata in zip(
            result.get("ids", []),
            result.get("documents", []),
            result.get("metadatas", []),
            strict=False,
        ):
            docs.append(Document(id=doc_id, text=text, metadata=metadata or {}))
        return docs
