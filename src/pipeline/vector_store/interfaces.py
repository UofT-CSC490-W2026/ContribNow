from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

# floating[Any] to allow arbitrary precision
FloatVector = NDArray[np.floating[np.generic]]


@dataclass(frozen=True)
class VectorRecord:
    vector: FloatVector
    repo_slug: str
    file_path: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class SearchResult:
    # Higher score = better match.
    score: float
    repo_slug: str
    file_path: str
    start_line: int
    end_line: int
    vector: FloatVector | None


class VectorStore(Protocol):
    def upsert(self, records: list[VectorRecord]) -> int:
        """Insert or update a batch of vector records and return written count."""

    def delete_by_repo(self, repo_slug: str) -> int:
        """Delete all records for a repo. Returns number removed."""

    def search(
        self,
        query_vector: FloatVector,
        k: int = 5,
        *,
        repo_slug: str | None = None,
        file_path: str | None = None,
    ) -> list[SearchResult]:
        """Return top-k results for a query vector with optional filters."""
