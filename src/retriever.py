from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

from src.config import AppConfig
from src.embeddings import EmbeddingModel
from src.models import Document, SearchResult
from src.vector_store import ChromaVectorStore


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_/-]+", text.lower())


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = np.array(list(scores.values()), dtype="float32")
    max_value = float(values.max())
    min_value = float(values.min())
    if max_value == min_value:
        return {key: 1.0 for key in scores}
    return {key: (value - min_value) / (max_value - min_value) for key, value in scores.items()}


class SimpleBM25:
    def __init__(self, tokenized_documents: list[list[str]]) -> None:
        self.tokenized_documents = tokenized_documents
        self.doc_count = len(tokenized_documents)
        self.avg_doc_length = (
            sum(len(doc) for doc in tokenized_documents) / self.doc_count
            if self.doc_count
            else 0.0
        )
        self.term_frequencies = [Counter(doc) for doc in tokenized_documents]
        doc_frequencies: Counter[str] = Counter()
        for doc in tokenized_documents:
            doc_frequencies.update(set(doc))
        self.idf = {
            term: math.log(1 + (self.doc_count - freq + 0.5) / (freq + 0.5))
            for term, freq in doc_frequencies.items()
        }

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        k1 = 1.5
        b = 0.75
        scores = []
        for doc, frequencies in zip(self.tokenized_documents, self.term_frequencies, strict=False):
            doc_length = len(doc) or 1
            score = 0.0
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if not frequency:
                    continue
                numerator = frequency * (k1 + 1)
                denominator = frequency + k1 * (
                    1 - b + b * doc_length / (self.avg_doc_length or 1)
                )
                score += self.idf.get(token, 0.0) * numerator / denominator
            scores.append(score)
        return scores


class HybridRetriever:
    def __init__(self, config: AppConfig) -> None:
        self.embedding_model = EmbeddingModel(config.embedding_model)
        self.vector_store = ChromaVectorStore(config.vector_db_dir, self.embedding_model)
        self.documents_by_id: dict[str, Document] = {}
        self.bm25: SimpleBM25 | None = None
        self._refresh_keyword_index()

    def count(self) -> int:
        return len(self.documents_by_id)

    def index_documents(self, documents: list[Document]) -> None:
        self.vector_store.upsert(documents)
        self._refresh_keyword_index()

    def _refresh_keyword_index(self) -> None:
        docs = self.vector_store.get_all()
        self.documents_by_id = {doc.id: doc for doc in docs}
        if docs:
            self.bm25 = SimpleBM25([tokenize(doc.text) for doc in docs])
        else:
            self.bm25 = None

    def _keyword_search(self, question: str) -> dict[str, float]:
        if not self.bm25 or not self.documents_by_id:
            return {}
        tokenized = tokenize(question)
        scores = self.bm25.get_scores(tokenized)
        ids = list(self.documents_by_id.keys())
        raw = {doc_id: float(score) for doc_id, score in zip(ids, scores, strict=False) if score > 0}
        return normalize_scores(raw)

    def search(self, question: str, mode: str, top_k: int) -> list[SearchResult]:
        keyword_scores = self._keyword_search(question)
        vector_scores = self.vector_store.query(question, top_k=max(top_k * 4, 20))

        candidate_ids = set(keyword_scores) | set(vector_scores)
        if not candidate_ids:
            return []

        results: list[SearchResult] = []
        for doc_id in candidate_ids:
            keyword_score = keyword_scores.get(doc_id, 0.0)
            vector_score = vector_scores.get(doc_id, 0.0)
            if mode == "Text only":
                score = keyword_score
            elif mode == "Meaning only":
                score = vector_score
            else:
                score = (0.5 * keyword_score) + (0.5 * vector_score)

            document = self.documents_by_id.get(doc_id)
            if document and score > 0:
                results.append(
                    SearchResult(
                        document=document,
                        score=score,
                        keyword_score=keyword_score,
                        vector_score=vector_score,
                    )
                )

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]
