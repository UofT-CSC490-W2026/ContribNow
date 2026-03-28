import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

import numpy as np

from src.pipeline.chunking import (
    Chunk,
    ChunkingConfig,
    DefaultLanguageRegistry,
    NaiveChunkingStrategy,
)
from src.pipeline.embedding import (
    EmbeddingConfig,
    EmbeddingRequest,
    LocalEmbeddingProvider,
)
from src.pipeline.indexing import index_repo, index_repo_in_memory
from src.pipeline.indexing import indexer as indexer_module
from src.pipeline.indexing.indexer import (
    _build_requests,
    _chunk_file,
    _iter_files,
    _record_from_embedding_metadata,
    _simple_token_counter,
    build_language_registry,
)
from src.pipeline.vector_store import InMemoryVectorStore


class DummyChunkingStrategy:
    name = "dummy"

    def __init__(self) -> None:
        self.called: list[dict[str, Any]] = []

    def supports_language(self, language: str | None) -> bool:
        return True

    def chunk(self, request, language, config):
        self.called.append({"request": request, "language": language})
        return [
            Chunk(
                chunk_id="c1",
                repo_slug=request.repo_slug,
                file_path=request.file_path,
                language=language,
                strategy=self.name,
                start_byte=0,
                end_byte=len(request.content),
                start_line=1,
                end_line=1,
                content=request.content,
            )
        ]


class TestIndexingInMemory(unittest.TestCase):
    def test_indexes_and_searches(self) -> None:
        provider = LocalEmbeddingProvider()
        embedding_config = EmbeddingConfig(model="local-test", batch_size=4)
        chunking_config = ChunkingConfig(
            max_bytes=200, overlap_bytes=0, min_split_bytes=50
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            file_path = repo_root / "app.py"
            file_path.write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

            ingest = {
                "repo_slug": "demo-repo",
                "head_commit": "abc123",
                "files": ["app.py"],
            }
            ingest_path = root / "ingest.json"
            ingest_path.write_text(json.dumps(ingest), encoding="utf-8")

            store, stats = index_repo_in_memory(
                ingest_json_path=ingest_path,
                repo_root=repo_root,
                embedding_provider=provider,
                embedding_config=embedding_config,
                chunking_config=chunking_config,
            )

            self.assertEqual(stats.files_seen, 1)
            self.assertEqual(stats.files_indexed, 1)
            self.assertGreater(stats.chunks_indexed, 0)
            self.assertEqual(stats.vectors_upserted, stats.chunks_indexed)

            query_req = EmbeddingRequest(text="def greet():", metadata={})
            query_vec = provider.embed([query_req], embedding_config).vectors[0]
            results = store.search(query_vec, k=3, repo_slug="demo-repo")

            self.assertGreater(len(results), 0)
            self.assertEqual(results[0].head_commit, "abc123")
            self.assertEqual(results[0].file_path, "app.py")

    def test_delete_by_repo(self) -> None:
        provider = LocalEmbeddingProvider()
        embedding_config = EmbeddingConfig(model="local-test", batch_size=4)
        chunking_config = ChunkingConfig(
            max_bytes=200, overlap_bytes=0, min_split_bytes=50
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / "a.py").write_text("print('a')\n", encoding="utf-8")
            (repo_root / "b.py").write_text("print('b')\n", encoding="utf-8")

            ingest = {
                "repo_slug": "demo-repo",
                "head_commit": "def456",
                "files": ["a.py", "b.py"],
            }
            ingest_path = root / "ingest.json"
            ingest_path.write_text(json.dumps(ingest), encoding="utf-8")

            store, stats = index_repo_in_memory(
                ingest_json_path=ingest_path,
                repo_root=repo_root,
                embedding_provider=provider,
                embedding_config=embedding_config,
                chunking_config=chunking_config,
            )

            self.assertGreater(stats.vectors_upserted, 0)
            removed = store.delete_by_repo("demo-repo")
            self.assertEqual(removed, stats.vectors_upserted)

            query_req = EmbeddingRequest(text="print('a')", metadata={})
            query_vec = provider.embed([query_req], embedding_config).vectors[0]
            results = store.search(query_vec, k=3, repo_slug="demo-repo")
            self.assertEqual(len(results), 0)


class TestIndexerHelpers(unittest.TestCase):
    def test_simple_token_counter_and_build_requests_and_record(self) -> None:
        self.assertEqual(_simple_token_counter("hello world", "any"), 2)

        chunk = Chunk(
            chunk_id="c1",
            repo_slug="demo",
            file_path="app.py",
            language="python",
            strategy="naive",
            start_byte=0,
            end_byte=5,
            start_line=1,
            end_line=1,
            content=b"hello",
        )
        requests = _build_requests([chunk])
        self.assertEqual(requests[0].text, "hello")
        self.assertEqual(requests[0].metadata["file_path"], "app.py")

        record = _record_from_embedding_metadata(
            vector=[1.0, 2.0],
            metadata={
                "repo_slug": "demo",
                "head_commit": 123,
                "file_path": "app.py",
                "start_line": "1",
                "end_line": 2,
            },
        )
        self.assertEqual(record.repo_slug, "demo")
        self.assertEqual(record.head_commit, "123")
        self.assertEqual(record.start_line, 1)
        self.assertEqual(record.end_line, 2)
        self.assertEqual(record.vector.dtype, np.float32)

    def test_build_language_registry_handles_strategy_errors(self) -> None:
        class Boom:
            def __init__(self) -> None:
                raise RuntimeError("boom")

        with (
            patch.object(indexer_module, "TSPyChunkingStrategy", Boom),
            patch.object(indexer_module, "TSJavaScriptChunkingStrategy", Boom),
            patch.object(indexer_module, "TSJSXChunkingStrategy", Boom),
            patch.object(indexer_module, "TSJavaChunkingStrategy", Boom),
        ):
            registry = build_language_registry()
        self.assertIsInstance(registry, DefaultLanguageRegistry)

    def test_chunk_file_uses_registered_strategy(self) -> None:
        registry = DefaultLanguageRegistry()
        strategy = DummyChunkingStrategy()
        registry.register_strategy("python", strategy)

        chunks = _chunk_file(
            repo_slug="demo",
            rel_path="app.py",
            content=b"print('hi')\n",
            registry=registry,
            default_strategy=NaiveChunkingStrategy(),
            config=ChunkingConfig(max_bytes=200, overlap_bytes=0, min_split_bytes=50),
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].file_path, "app.py")
        self.assertEqual(strategy.called[0]["language"], "python")

    def test_iter_files_with_hashes_filters(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "small.txt").write_text("hi", encoding="utf-8")
            (root / "too_big.txt").write_text("x" * 20, encoding="utf-8")
            (root / "stat_error.txt").write_text("ok", encoding="utf-8")

            manifest = {
                "files_with_hashes": [
                    "not-a-dict",
                    {"path": 123},
                    {"path": "small.txt", "content_hash": ""},
                    {"path": "missing.txt", "content_hash": "hash"},
                    {"path": "big.txt", "content_hash": "hash", "size_bytes": 999},
                    {"path": "too_big.txt", "content_hash": "hash"},
                    {"path": "stat_error.txt", "content_hash": "hash"},
                    {"path": "small.txt", "content_hash": "hash", "size_bytes": 2},
                ]
            }

            original_stat = Path.stat

            def stat_side_effect(self: Path, *args, **kwargs):
                if self.name == "stat_error.txt":
                    raise OSError("stat failed")
                return original_stat(self, *args, **kwargs)

            def exists_side_effect(self: Path, *args, **kwargs):
                if self.name == "missing.txt":
                    return False
                return True

            def is_file_side_effect(self: Path, *args, **kwargs):
                return self.name != "missing.txt"

            with (
                patch.object(Path, "stat", new=stat_side_effect),
                patch.object(Path, "exists", new=exists_side_effect),
                patch.object(Path, "is_file", new=is_file_side_effect),
            ):
                results = list(
                    _iter_files(
                        manifest,
                        root,
                        max_file_bytes=5,
                        skip_empty_hashes=True,
                    )
                )

            self.assertEqual([rel for rel, _ in results], ["small.txt"])

    def test_iter_files_with_hashes_limit(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.txt").write_text("a", encoding="utf-8")
            (root / "b.txt").write_text("b", encoding="utf-8")

            manifest = {
                "files_with_hashes": [
                    {"path": "a.txt", "content_hash": "hash", "size_bytes": 1},
                    {"path": "b.txt", "content_hash": "hash", "size_bytes": 1},
                ]
            }

            results = list(_iter_files(manifest, root, limit=1))
            self.assertEqual(len(results), 1)

    def test_iter_files_list_filters(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "ok1.txt").write_text("ok", encoding="utf-8")
            (root / "ok2.txt").write_text("ok", encoding="utf-8")
            (root / "big.txt").write_text("x" * 20, encoding="utf-8")
            (root / "stat_error.txt").write_text("err", encoding="utf-8")

            manifest = {
                "files": [
                    123,
                    str(Path("/abs/path")),
                    "badresolve.txt",
                    "../escape.txt",
                    "missing.txt",
                    "stat_error.txt",
                    "big.txt",
                    "ok1.txt",
                    "ok2.txt",
                ]
            }

            original_resolve = Path.resolve
            original_stat = Path.stat

            def resolve_side_effect(self: Path):
                if self.name == "badresolve.txt":
                    raise OSError("resolve failed")
                return original_resolve(self)

            def stat_side_effect(self: Path, *args, **kwargs):
                if self.name == "stat_error.txt":
                    raise OSError("stat failed")
                return original_stat(self, *args, **kwargs)

            def exists_side_effect(self: Path, *args, **kwargs):
                if self.name == "missing.txt":
                    return False
                return True

            def is_file_side_effect(self: Path, *args, **kwargs):
                return self.name != "missing.txt"

            with (
                patch.object(Path, "resolve", new=resolve_side_effect),
                patch.object(Path, "stat", new=stat_side_effect),
                patch.object(Path, "exists", new=exists_side_effect),
                patch.object(Path, "is_file", new=is_file_side_effect),
            ):
                results = list(_iter_files(manifest, root, max_file_bytes=5))

            self.assertEqual([rel for rel, _ in results], ["ok1.txt", "ok2.txt"])

    def test_iter_files_list_not_list(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            manifest = {"files": "not-a-list"}
            self.assertEqual(list(_iter_files(manifest, root)), [])

    def test_iter_files_list_limit(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "ok1.txt").write_text("ok", encoding="utf-8")
            (root / "ok2.txt").write_text("ok", encoding="utf-8")

            manifest = {"files": ["ok1.txt", "ok2.txt"]}
            results = list(_iter_files(manifest, root, limit=1))
            self.assertEqual(len(results), 1)

    def test_index_repo_raises_without_head_commit(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / "app.py").write_text("print('hi')\n", encoding="utf-8")

            ingest = {"repo_slug": "demo", "files": ["app.py"]}
            ingest_path = root / "ingest.json"
            ingest_path.write_text(json.dumps(ingest), encoding="utf-8")

            with self.assertRaises(ValueError):
                index_repo(
                    ingest_json_path=ingest_path,
                    repo_root=repo_root,
                    store=InMemoryVectorStore(),
                    embedding_provider=LocalEmbeddingProvider(),
                    embedding_config=EmbeddingConfig(model="local-test"),
                    chunking_config=ChunkingConfig(
                        max_bytes=200, overlap_bytes=0, min_split_bytes=50
                    ),
                    registry=DefaultLanguageRegistry(),
                )

    def test_index_repo_skips_unreadable_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / "app.py").write_text("print('hi')\n", encoding="utf-8")

            ingest = {
                "repo_slug": "demo",
                "head_commit": "abc123",
                "files": ["app.py"],
            }
            ingest_path = root / "ingest.json"
            ingest_path.write_text(json.dumps(ingest), encoding="utf-8")

            original_read_bytes = Path.read_bytes

            def read_bytes_side_effect(self: Path):
                if self.name == "app.py":
                    raise OSError("read failed")
                return original_read_bytes(self)

            with patch.object(Path, "read_bytes", new=read_bytes_side_effect):
                stats = index_repo(
                    ingest_json_path=ingest_path,
                    repo_root=repo_root,
                    store=InMemoryVectorStore(),
                    embedding_provider=LocalEmbeddingProvider(),
                    embedding_config=EmbeddingConfig(model="local-test"),
                    chunking_config=ChunkingConfig(
                        max_bytes=200, overlap_bytes=0, min_split_bytes=50
                    ),
                    registry=DefaultLanguageRegistry(),
                )

            self.assertEqual(stats.files_seen, 1)
            self.assertEqual(stats.files_indexed, 0)

    def test_index_repo_skips_empty_chunks(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            (repo_root / "app.py").write_text("print('hi')\n", encoding="utf-8")

            ingest = {
                "repo_slug": "demo",
                "head_commit": "abc123",
                "files": ["app.py"],
            }
            ingest_path = root / "ingest.json"
            ingest_path.write_text(json.dumps(ingest), encoding="utf-8")

            with patch.object(indexer_module, "_chunk_file", return_value=[]):
                stats = index_repo(
                    ingest_json_path=ingest_path,
                    repo_root=repo_root,
                    store=InMemoryVectorStore(),
                    embedding_provider=LocalEmbeddingProvider(),
                    embedding_config=EmbeddingConfig(model="local-test"),
                    chunking_config=ChunkingConfig(
                        max_bytes=200, overlap_bytes=0, min_split_bytes=50
                    ),
                    registry=DefaultLanguageRegistry(),
                )

            self.assertEqual(stats.files_seen, 1)
            self.assertEqual(stats.files_indexed, 0)


if __name__ == "__main__":
    unittest.main()
