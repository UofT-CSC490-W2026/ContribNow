from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

from src.pipeline.chunking import (
    Chunk,
    ChunkingConfig,
    ChunkingStrategy,
    DefaultLanguageRegistry,
    FileChunkRequest,
    LanguageRegistry,
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
from src.pipeline.utils import read_json
from src.pipeline.vector_store import InMemoryVectorStore, VectorRecord, VectorStore

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
    *,
    max_file_bytes: int | None = None,
    skip_empty_hashes: bool = True,
) -> Iterable[tuple[str, Path]]:
    files_with_hashes = manifest.get("files_with_hashes")
    if isinstance(files_with_hashes, list):
        count = 0
        for entry in files_with_hashes:
            if not isinstance(entry, dict):
                continue
            rel = entry.get("path")
            if not isinstance(rel, str):
                continue
            content_hash = entry.get("content_hash")
            if skip_empty_hashes and (
                not isinstance(content_hash, str) or content_hash == ""
            ):
                continue
            size_bytes = entry.get("size_bytes")
            size_value = size_bytes if isinstance(size_bytes, int) else None
            if (
                max_file_bytes is not None
                and size_value is not None
                and size_value > max_file_bytes
            ):
                continue
            path = repo_root / rel
            if not path.exists() or not path.is_file():
                continue
            if max_file_bytes is not None and size_value is None:
                try:
                    if path.stat().st_size > max_file_bytes:
                        continue
                except OSError:
                    continue
            yield rel, path
            count += 1
            if limit is not None and count >= limit:
                break
        return

    files = manifest.get("files")
    if not isinstance(files, list):
        return
    count = 0
    for rel in files:
        if not isinstance(rel, str):
            continue
        rel_path = Path(rel)
        # Disallow absolute paths from the manifest.
        if rel_path.is_absolute():
            continue
        try:
            # Resolve to eliminate ".." and follow symlinks.
            path = (repo_root / rel_path).resolve()
        except OSError:
            # If the path cannot be resolved, skip it.
            continue
        try:
            # Ensure the resolved path is within the repo root.
            path.relative_to(repo_root.resolve())
        except ValueError:
            # Path escapes the repo root; skip it.
            continue
        if not path.exists() or not path.is_file():
            continue
        if max_file_bytes is not None:
            try:
                if path.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
        yield rel, path
        count += 1
        if limit is not None and count >= limit:
            break


def _chunk_file(
    repo_slug: str,
    rel_path: str,
    content: bytes,
    registry: LanguageRegistry,
    default_strategy: ChunkingStrategy,
    config: ChunkingConfig,
) -> list[Chunk]:
    language = registry.detect(
        rel_path, content[:1024].decode("utf-8", errors="replace")
    )
    strategy = registry.get_strategy(language or "") or default_strategy
    request = FileChunkRequest(
        repo_slug=repo_slug,
        file_path=rel_path,
        content=content,
    )
    return strategy.chunk(request, language, config)


def _build_requests(chunks: Iterable[Chunk]) -> list[EmbeddingRequest]:
    requests: list[EmbeddingRequest] = []
    for chunk in chunks:
        requests.append(
            EmbeddingRequest(
                text=chunk.content.decode("utf-8", errors="replace"),
                metadata={
                    "repo_slug": chunk.repo_slug,
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                },
            )
        )
    return requests


def _record_from_embedding_metadata(
    *, vector: list[float], metadata: dict[str, Any]
) -> VectorRecord:
    return VectorRecord(
        vector=np.asarray(vector, dtype=np.float32),
        repo_slug=str(metadata["repo_slug"]),
        file_path=str(metadata["file_path"]),
        start_line=int(metadata["start_line"]),
        end_line=int(metadata["end_line"]),
    )


def index_repo(
    ingest_json_path: Path,
    repo_root: Path,
    store: VectorStore,
    embedding_provider: EmbeddingProvider,
    embedding_config: EmbeddingConfig,
    chunking_config: ChunkingConfig,
    registry: LanguageRegistry,
    default_strategy: ChunkingStrategy = NaiveChunkingStrategy(),
    file_limit: int | None = None,
    max_file_bytes: int | None = None,
    skip_empty_hashes: bool = True,
    token_counter: TokenCounter | None = None,
) -> IndexingStats:
    manifest = read_json(Path(ingest_json_path))
    repo_slug = str(manifest.get("repo_slug") or repo_root.name)
    token_counter = token_counter or _simple_token_counter

    files_seen = 0
    files_indexed = 0
    chunks_indexed = 0
    batches_sent = 0
    vectors_upserted = 0

    for rel_path, path in _iter_files(
        manifest,
        Path(repo_root),
        limit=file_limit,
        max_file_bytes=max_file_bytes,
        skip_empty_hashes=skip_empty_hashes,
    ):
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
            token_counter=token_counter
            if embedding_config.max_tokens is not None
            else None,
        )
        for batch in batches:
            batches_sent += 1
            result = embedding_provider.embed(batch, embedding_config)
            records = [
                _record_from_embedding_metadata(vector=vector, metadata=meta)
                for vector, meta in zip(result.vectors, result.metadata, strict=True)
            ]
            vectors_upserted += store.upsert(records)

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
    max_file_bytes: int | None = None,
    skip_empty_hashes: bool = True,
) -> tuple[InMemoryVectorStore, IndexingStats]:
    store = InMemoryVectorStore()
    registry = build_language_registry()
    stats = index_repo(
        ingest_json_path=ingest_json_path,
        repo_root=repo_root,
        store=store,
        embedding_provider=embedding_provider,
        embedding_config=embedding_config,
        chunking_config=chunking_config,
        registry=registry,
        file_limit=file_limit,
        max_file_bytes=max_file_bytes,
        skip_empty_hashes=skip_empty_hashes,
    )
    return store, stats
