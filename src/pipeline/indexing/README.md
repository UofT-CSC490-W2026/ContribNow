# Indexing Pipeline

This package wires together chunking + embedding + vector store upsert for RAG indexing.
It is designed as a lightweight orchestration layer on top of the existing chunking and
embedding libraries.

## Overview

Flow:

1. Read `ingest.json` (from `src/pipeline/ingest.py`).
2. Load each file and chunk it using language-aware strategies.
3. Build `EmbeddingRequest` objects per chunk.
4. Batch and embed via an `EmbeddingProvider`.
5. Upsert vectors + minimal location fields into a `VectorStore`.

## Public API

Import from:

```python
from src.pipeline.indexing import (
    IndexingStats,
    InMemoryVectorStore,
    VectorStore,
    index_repo,
    index_repo_in_memory,
)
```

## Core Types

### `IndexingStats`

Returned by `index_repo(...)` and `index_repo_in_memory(...)`:

- `files_seen`: manifest entries that resolved to existing files and were processed
- `files_indexed`: files that produced at least one chunk
- `chunks_indexed`: total chunks created
- `batches_sent`: embedding batches sent
- `vectors_upserted`: vectors written to the store

### `VectorStore`

Protocol implemented by vector stores (in-memory and pgvector):

- `upsert(records: list[VectorRecord])`
- `delete_by_repo(repo_slug: str) -> int`
- `search(query_vector: np.ndarray, k: int = 5, repo_slug: str | None = None, file_path: str | None = None, head_commit: str | None = None)`

### `InMemoryVectorStore`

Simple in-process store used for tests and local wiring. Supports cosine similarity search
with explicit field filters.

## Indexing Functions

### `index_repo(...)`

Orchestrates ingest -> chunk -> embed -> upsert.

Parameters:

- `ingest_json_path`: path to the ingest manifest
- `repo_root`: path to the repo checkout
- `store`: any `VectorStore`
- `embedding_provider`: provider instance
- `embedding_config`: `EmbeddingConfig`
- `chunking_config`: `ChunkingConfig`
- `file_limit`: optional file count limit
- `max_file_bytes`: optional skip threshold for large files
- `skip_empty_hashes`: skip `files_with_hashes` entries with empty `content_hash`

### `index_repo_in_memory(...)`

Helper that builds an `InMemoryVectorStore` and runs `index_repo(...)`.

## CLI

Run the in-memory indexer:

```bash
python -m src.pipeline.indexing.cli \
  --ingest-path path/to/ingest.json \
  --repo-root path/to/repo/checkout \
  --provider local \
  --model dummy-model
```

Provider options:

- `local` (deterministic fake vectors; no external deps)
- `huggingface` (requires `sentence-transformers`)
- `openai` (requires `openai` + `tiktoken`)

## Strategy Registration

`index_repo(...)` uses `build_language_registry()` which registers Tree-sitter
strategies when available and falls back to `NaiveChunkingStrategy` otherwise.

## Notes

- Use `InMemoryVectorStore` for tests and local validation.
- Use `PgVectorStore` for Postgres/pgvector-backed persistence.
- Pseudo-code example:

```
from src.pipeline.embedding import EmbeddingConfig
from src.pipeline.embedding.providers.openai_provider import OpenAIEmbeddingProvider
from src.pipeline.vector_store import PgVectorStore

provider = OpenAIEmbeddingProvider()
config = EmbeddingConfig(model="text-embedding-3-large")
store = PgVectorStore(db_url=...)

query_vec = provider.embed(
    [EmbeddingRequest(text=query, metadata={})],
    config
).vectors[0]

results = store.search(query_vec, k=12, repo_slug="demo-repo")
context = build_context(results, token_budget=3000)
```
