from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from src.pipeline.chunking import (
    ChunkingConfig,
    DefaultLanguageRegistry,
    FileChunkRequest,
    NaiveChunkingStrategy,
    TSJavaChunkingStrategy,
    TSJavaScriptChunkingStrategy,
    TSJSXChunkingStrategy,
    TSPyChunkingStrategy,
)
from src.pipeline.embedding import (
    EmbeddingConfig,
    EmbeddingProvider,
    EmbeddingRequest,
    batch_requests,
)
from src.pipeline.indexing.vector_store import InMemoryVectorStore, VectorRecord, VectorStore
from src.pipeline.utils import read_json

TokenCounter = Callable[[str, str], int]


@dataclass(frozen=True)
class IndexingStats:
    files_seen: int
    files_indexed: int
    chunks_indexed: int
    batches_sent: int
    vectors_upserted: int


def _simple_token_counter(text: str, model: str) -> int:
    _ = model
    return len(text.split())


def build_language_registry() -> DefaultLanguageRegistry:
    registry = DefaultLanguageRegistry()
    # Tree-sitter strategies are optional. Fail closed and fall back to naive.
    try:
        registry.register_strategy("python", TSPyChunkingStrategy())
    except Exception:
        pass
    try:
        registry.register_strategy("javascript", TSJavaScriptChunkingStrategy())
    except Exception:
        pass
    try:
        registry.register_strategy("jsx", TSJSXChunkingStrategy())
    except Exception:
        pass
    try:
        registry.register_strategy("java", TSJavaChunkingStrategy())
    except Exception:
        pass
    return registry


def _iter_files(
    manifest: dict[str, Any],
    repo_root: Path,
    limit: int | None = None,
) -> Iterable[tuple[str, Path]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        return []
    count = 0
    for rel in files:
        if not isinstance(rel, str):
            continue
        path = repo_root / rel
        if not path.exists() or not path.is_file():
            continue
        yield rel, path
        count += 1
        if limit is not None and count >= limit:
            break


def _chunk_file(
    repo_slug: str,
    rel_path: str,
    content: bytes,
    registry: DefaultLanguageRegistry,
    default_strategy: NaiveChunkingStrategy,
    config: ChunkingConfig,
) -> list[Any]:
    language = registry.detect(rel_path, content[:1024].decode("utf-8", errors="replace"))
    strategy = registry.get_strategy(language or "") or default_strategy
    request = FileChunkRequest(
        repo_slug=repo_slug,
        file_path=rel_path,
        content=content,
    )
    return strategy.chunk(request, language, config)


def _build_requests(chunks: Iterable[Any]) -> list[EmbeddingRequest]:
    requests: list[EmbeddingRequest] = []
    for chunk in chunks:
        text = chunk.content.decode("utf-8", errors="replace")
        requests.append(
            EmbeddingRequest(
                text=text,
                metadata={
                    "chunk_id": chunk.chunk_id,
                    "repo_slug": chunk.repo_slug,
                    "file_path": chunk.file_path,
                    "language": chunk.language,
                    "strategy": chunk.strategy,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": text,
                },
            )
        )
    return requests


def index_repo(
    ingest_json_path: Path,
    repo_root: Path,
    store: VectorStore,
    embedding_provider: EmbeddingProvider,
    embedding_config: EmbeddingConfig,
    chunking_config: ChunkingConfig,
    *,
    registry: DefaultLanguageRegistry | None = None,
    default_strategy: NaiveChunkingStrategy | None = None,
    file_limit: int | None = None,
    token_counter: TokenCounter | None = None,
) -> IndexingStats:
    manifest = read_json(Path(ingest_json_path))
    repo_slug = str(manifest.get("repo_slug") or repo_root.name)
    registry = registry or build_language_registry()
    default_strategy = default_strategy or NaiveChunkingStrategy()
    token_counter = token_counter or _simple_token_counter

    files_seen = 0
    files_indexed = 0
    chunks_indexed = 0
    batches_sent = 0
    vectors_upserted = 0

    for rel_path, path in _iter_files(manifest, Path(repo_root), limit=file_limit):
        files_seen += 1
        try:
            content = path.read_bytes()
        except OSError:
            continue

        chunks = _chunk_file(
            repo_slug=repo_slug,
            rel_path=rel_path,
            content=content,
            registry=registry,
            default_strategy=default_strategy,
            config=chunking_config,
        )
        if not chunks:
            continue
        files_indexed += 1
        chunks_indexed += len(chunks)

        requests = _build_requests(chunks)
        batches = batch_requests(
            requests,
            embedding_config,
            token_counter=token_counter if embedding_config.max_tokens is not None else None,
        )
        for batch in batches:
            batches_sent += 1
            result = embedding_provider.embed(batch, embedding_config)
            records = [
                VectorRecord(vector=vector, metadata=meta)
                for vector, meta in zip(result.vectors, result.metadata, strict=True)
            ]
            store.upsert(records)
            vectors_upserted += len(records)

    return IndexingStats(
        files_seen=files_seen,
        files_indexed=files_indexed,
        chunks_indexed=chunks_indexed,
        batches_sent=batches_sent,
        vectors_upserted=vectors_upserted,
    )


def index_repo_in_memory(
    ingest_json_path: Path,
    repo_root: Path,
    embedding_provider: EmbeddingProvider,
    embedding_config: EmbeddingConfig,
    chunking_config: ChunkingConfig,
    *,
    file_limit: int | None = None,
) -> tuple[InMemoryVectorStore, IndexingStats]:
    store = InMemoryVectorStore()
    stats = index_repo(
        ingest_json_path=ingest_json_path,
        repo_root=repo_root,
        store=store,
        embedding_provider=embedding_provider,
        embedding_config=embedding_config,
        chunking_config=chunking_config,
        file_limit=file_limit,
    )
    return store, stats
