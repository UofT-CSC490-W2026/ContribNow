from __future__ import annotations

import numpy as np

from src.pipeline.vector_store.interfaces import FloatVector, SearchResult, VectorRecord


def _cosine_similarity(a: FloatVector, b: FloatVector) -> float:
    if a.shape != b.shape:
        raise ValueError("Vectors must have the same dimension for cosine similarity.")
    dot = float(np.dot(a, b))
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryVectorStore:
    """
    Simple in-memory vector store for local testing and pipeline wiring.
    """

    def __init__(self) -> None:
        self._records: list[VectorRecord] = []
        self._by_span: dict[tuple[str, str, str, int, int], int] = {}

    def upsert(self, records: list[VectorRecord]) -> int:
        for record in records:
            span_key = (
                record.repo_slug,
                record.head_commit,
                record.file_path,
                int(record.start_line),
                int(record.end_line),
            )
            if span_key in self._by_span:
                idx = self._by_span[span_key]
                self._records[idx] = record
            else:
                self._records.append(record)
                self._by_span[span_key] = len(self._records) - 1
        return len(records)

    def delete_by_repo(self, repo_slug: str) -> int:
        kept: list[VectorRecord] = []
        removed = 0
        for record in self._records:
            if record.repo_slug == repo_slug:
                removed += 1
            else:
                kept.append(record)
        self._records = kept
        self._by_span = {
            (
                record.repo_slug,
                record.head_commit,
                record.file_path,
                record.start_line,
                record.end_line,
            ): idx
            for idx, record in enumerate(self._records)
        }
        return removed

    def search(
        self,
        query_vector: FloatVector,
        k: int = 5,
        *,
        repo_slug: str | None = None,
        head_commit: str | None = None,
        file_path: str | None = None,
    ) -> list[SearchResult]:
        if k <= 0:
            return []
        query = np.asarray(query_vector, dtype=np.float32)
        if query.ndim != 1 or query.size == 0:
            return []

        scored: list[SearchResult] = []
        for record in self._records:
            if repo_slug is not None and record.repo_slug != repo_slug:
                continue
            if head_commit is not None and record.head_commit != head_commit:
                continue
            if file_path is not None and record.file_path != file_path:
                continue

            score = _cosine_similarity(query, record.vector)
            scored.append(
                SearchResult(
                    score=score,
                    repo_slug=record.repo_slug,
                    head_commit=record.head_commit,
                    file_path=record.file_path,
                    start_line=record.start_line,
                    end_line=record.end_line,
                    vector=record.vector,
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:k]
