# Vector Store Library

Shared vector-store interfaces and implementations used by indexing.
Vectors are represented as NumPy 1D arrays.

## Public API

```python
from src.pipeline.vector_store import (
    InMemoryVectorStore,
    PgVectorStore,
    SearchResult,
    VectorRecord,
    VectorStore,
)
```

## Interface

- `VectorRecord(vector, repo_slug, file_path, start_line, end_line, head_commit)`: upsert payload (`vector` is `np.ndarray`)
- `SearchResult(score, repo_slug, file_path, start_line, end_line, vector=None, head_commit=None)`: search hit (`score` higher is better)
- `VectorStore` protocol:
  - `upsert(records) -> int`
  - `delete_by_repo(repo_slug) -> int`
  - `search(query_vector, k=5, repo_slug=None, file_path=None, head_commit=None) -> list[SearchResult]`

## Implementations

- `InMemoryVectorStore`: deterministic local store for tests/dev.
- `PgVectorStore`: Postgres/pgvector backend.
  - Requires `db_url` in constructor.
  - `ensure_schema()` creates extension/table/indexes.
  - Uses `(repo_slug, head_commit, file_path, start_line, end_line)` as the deterministic upsert key.
