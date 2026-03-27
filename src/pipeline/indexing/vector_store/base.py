from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class VectorRecord:
    vector: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SearchResult:
    score: float
    metadata: dict[str, Any]
    vector: list[float] | None = None


class VectorStore(Protocol):
    def upsert(self, records: list[VectorRecord]) -> None:
        """Insert or update a batch of vector records."""

    def delete_by_repo(self, repo_slug: str) -> int:
        """Delete all records for a repo. Returns number removed."""

    def search(
        self,
        query_vector: list[float],
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Return top-k results for a query vector with optional metadata filters."""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError("Vectors must have the same dimension for cosine similarity.")
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for av, bv in zip(a, b, strict=True):
        dot += av * bv
        norm_a += av * av
        norm_b += bv * bv
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


class InMemoryVectorStore:
    """
    Simple in-memory vector store for local testing and pipeline wiring.
    """

    def __init__(self) -> None:
        self._records: list[VectorRecord] = []
        self._by_chunk_id: dict[str, int] = {}

    def upsert(self, records: list[VectorRecord]) -> None:
        for record in records:
            chunk_id = str(record.metadata.get("chunk_id") or "")
            if chunk_id and chunk_id in self._by_chunk_id:
                idx = self._by_chunk_id[chunk_id]
                self._records[idx] = record
            else:
                self._records.append(record)
                if chunk_id:
                    self._by_chunk_id[chunk_id] = len(self._records) - 1

    def delete_by_repo(self, repo_slug: str) -> int:
        kept: list[VectorRecord] = []
        removed = 0
        for record in self._records:
            if str(record.metadata.get("repo_slug")) == repo_slug:
                removed += 1
            else:
                kept.append(record)
        self._records = kept
        self._by_chunk_id = {
            str(record.metadata.get("chunk_id")): idx
            for idx, record in enumerate(self._records)
            if record.metadata.get("chunk_id")
        }
        return removed

    def search(
        self,
        query_vector: list[float],
        k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        if k <= 0:
            return []

        def match_filters(metadata: dict[str, Any]) -> bool:
            if not filters:
                return True
            for key, value in filters.items():
                if metadata.get(key) != value:
                    return False
            return True

        scored: list[SearchResult] = []
        for record in self._records:
            if not match_filters(record.metadata):
                continue
            score = _cosine_similarity(query_vector, record.vector)
            scored.append(
                SearchResult(score=score, metadata=record.metadata, vector=record.vector)
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:k]

# TODO: Create PgVectorStore to integrate RAG with our RDS