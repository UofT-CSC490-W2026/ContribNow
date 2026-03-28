import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.pipeline.chunking import Chunk, ChunkingConfig, FileChunkRequest
from src.pipeline.embedding import EmbeddingConfig, EmbeddingResult
from src.pipeline.indexing.indexer import index_repo


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _make_chunk(
    *,
    repo_slug: str,
    file_path: str,
    content: bytes,
    start_line: int = 1,
    end_line: int = 1,
) -> Chunk:
    return Chunk(
        chunk_id=f"{file_path}:{start_line}:{end_line}",
        repo_slug=repo_slug,
        file_path=file_path,
        language="python",
        strategy="fake",
        start_byte=0,
        end_byte=len(content),
        start_line=start_line,
        end_line=end_line,
        content=content,
    )


class _FakeRegistry:
    def __init__(
        self, *, language: str | None = "python", strategy: object | None = None
    ) -> None:
        self._language = language
        self._strategy = strategy

    def detect(self, file_path: str, content_head: str | None = None) -> str | None:
        _ = file_path, content_head
        return self._language

    def register_strategy(self, language: str, strategy: object) -> None:
        _ = language, strategy

    def get_strategy(self, language: str) -> object | None:
        _ = language
        return self._strategy


class _StaticStrategy:
    def __init__(
        self,
        *,
        chunks_by_file: dict[str, list[Chunk]] | None = None,
        errors_by_file: dict[str, Exception] | None = None,
    ) -> None:
        self._chunks_by_file = chunks_by_file or {}
        self._errors_by_file = errors_by_file or {}

    @property
    def name(self) -> str:
        return "fake"

    def supports_language(self, language: str | None) -> bool:
        return True

    def chunk(
        self, request: FileChunkRequest, language: str | None, config: ChunkingConfig
    ) -> list[Chunk]:
        _ = language, config
        if request.file_path in self._errors_by_file:
            raise self._errors_by_file[request.file_path]
        return list(self._chunks_by_file.get(request.file_path, []))


class _CapturingProvider:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.seen_texts: list[str] = []

    @property
    def name(self) -> str:
        return "capturing"

    def embed(self, requests: list, config: EmbeddingConfig) -> EmbeddingResult:
        _ = config
        if self.error is not None:
            raise self.error
        self.seen_texts.extend(request.text for request in requests)
        return EmbeddingResult(
            vectors=[[0.1, 0.2] for _ in requests],
            metadata=[request.metadata for request in requests],
        )


class _CapturingStore:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.records = []

    def upsert(self, records: list) -> int:
        if self.error is not None:
            raise self.error
        self.records.extend(records)
        return len(records)

    def delete_by_repo(self, repo_slug: str) -> int:
        _ = repo_slug
        return 0

    def search(
        self,
        query_vector,
        k: int = 5,
        *,
        repo_slug=None,
        head_commit=None,
        file_path=None,
    ):
        _ = query_vector, k, repo_slug, head_commit, file_path
        return []


class TestIndexingFailures(unittest.TestCase):
    def _run_index_repo(
        self,
        *,
        manifest: dict[str, object],
        repo_files: dict[str, bytes],
        registry: object,
        provider: _CapturingProvider | None = None,
        store: _CapturingStore | None = None,
        skip_empty_hashes: bool = True,
        max_file_bytes: int | None = None,
        file_limit: int | None = None,
        token_counter=None,
        embedding_config: EmbeddingConfig | None = None,
    ):
        provider = provider or _CapturingProvider()
        store = store or _CapturingStore()
        embedding_config = embedding_config or EmbeddingConfig(
            model="dummy-model", batch_size=2
        )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            for rel_path, content in repo_files.items():
                _write(repo_root / rel_path, content)

            ingest_path = root / "ingest.json"
            ingest_path.write_text(json.dumps(manifest), encoding="utf-8")

            stats = index_repo(
                ingest_json_path=ingest_path,
                repo_root=repo_root,
                store=store,
                embedding_provider=provider,
                embedding_config=embedding_config,
                chunking_config=ChunkingConfig(
                    max_bytes=200, overlap_bytes=0, min_split_bytes=50
                ),
                registry=registry,
                skip_empty_hashes=skip_empty_hashes,
                max_file_bytes=max_file_bytes,
                file_limit=file_limit,
                token_counter=token_counter,
            )
            return stats, provider, store

    def test_missing_head_commit_raises(self) -> None:
        manifest = {"repo_slug": "demo-repo", "files": ["app.py"]}
        strategy = _StaticStrategy(
            chunks_by_file={
                "app.py": [
                    _make_chunk(
                        repo_slug="demo-repo",
                        file_path="app.py",
                        content=b"print('x')\n",
                    )
                ]
            }
        )

        with self.assertRaises(ValueError):
            self._run_index_repo(
                manifest=manifest,
                repo_files={"app.py": b"print('x')\n"},
                registry=_FakeRegistry(strategy=strategy),
            )

    def test_skips_empty_hashes_by_default(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files_with_hashes": [
                {"path": "app.py", "content_hash": "", "size_bytes": 11}
            ],
        }
        strategy = _StaticStrategy(
            chunks_by_file={
                "app.py": [
                    _make_chunk(
                        repo_slug="demo-repo",
                        file_path="app.py",
                        content=b"print('x')\n",
                    )
                ]
            }
        )

        stats, _, store = self._run_index_repo(
            manifest=manifest,
            repo_files={"app.py": b"print('x')\n"},
            registry=_FakeRegistry(strategy=strategy),
        )

        self.assertEqual(stats.files_seen, 0)
        self.assertEqual(stats.vectors_upserted, 0)
        self.assertEqual(store.records, [])

    def test_can_include_empty_hashes_when_disabled(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files_with_hashes": [
                {"path": "app.py", "content_hash": "", "size_bytes": 11}
            ],
        }
        strategy = _StaticStrategy(
            chunks_by_file={
                "app.py": [
                    _make_chunk(
                        repo_slug="demo-repo",
                        file_path="app.py",
                        content=b"print('x')\n",
                    )
                ]
            }
        )

        stats, _, store = self._run_index_repo(
            manifest=manifest,
            repo_files={"app.py": b"print('x')\n"},
            registry=_FakeRegistry(strategy=strategy),
            skip_empty_hashes=False,
        )

        self.assertEqual(stats.files_seen, 1)
        self.assertEqual(stats.vectors_upserted, 1)
        self.assertEqual(store.records[0].head_commit, "abc123")

    def test_legacy_manifest_skips_paths_outside_repo(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files": ["../escape.py", "app.py"],
        }
        strategy = _StaticStrategy(
            chunks_by_file={
                "app.py": [
                    _make_chunk(
                        repo_slug="demo-repo",
                        file_path="app.py",
                        content=b"print('x')\n",
                    )
                ]
            }
        )

        stats, _, _ = self._run_index_repo(
            manifest=manifest,
            repo_files={"app.py": b"print('x')\n"},
            registry=_FakeRegistry(strategy=strategy),
        )

        self.assertEqual(stats.files_seen, 1)
        self.assertEqual(stats.files_indexed, 1)

    def test_read_errors_skip_only_the_unreadable_file(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files": ["bad.py", "good.py"],
        }
        strategy = _StaticStrategy(
            chunks_by_file={
                "good.py": [
                    _make_chunk(
                        repo_slug="demo-repo",
                        file_path="good.py",
                        content=b"print('ok')\n",
                    )
                ]
            }
        )

        original_read_bytes = Path.read_bytes

        def _patched_read_bytes(path_self: Path) -> bytes:
            if path_self.name == "bad.py":
                raise OSError("simulated read failure")
            return original_read_bytes(path_self)

        with patch.object(Path, "read_bytes", _patched_read_bytes):
            stats, _, _ = self._run_index_repo(
                manifest=manifest,
                repo_files={"bad.py": b"print('bad')\n", "good.py": b"print('ok')\n"},
                registry=_FakeRegistry(strategy=strategy),
            )

        self.assertEqual(stats.files_seen, 2)
        self.assertEqual(stats.files_indexed, 1)
        self.assertEqual(stats.vectors_upserted, 1)

    def test_empty_chunk_output_does_not_send_embeddings(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files": ["app.py"],
        }

        stats, provider, store = self._run_index_repo(
            manifest=manifest,
            repo_files={"app.py": b"print('x')\n"},
            registry=_FakeRegistry(strategy=_StaticStrategy()),
        )

        self.assertEqual(stats.files_seen, 1)
        self.assertEqual(stats.files_indexed, 0)
        self.assertEqual(stats.batches_sent, 0)
        self.assertEqual(provider.seen_texts, [])
        self.assertEqual(store.records, [])

    def test_chunk_bytes_are_decoded_with_replacement(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files": ["app.py"],
        }
        chunk = _make_chunk(
            repo_slug="demo-repo",
            file_path="app.py",
            content=b"\xff\xfeprint('x')\n",
        )
        provider = _CapturingProvider()

        stats, provider, _ = self._run_index_repo(
            manifest=manifest,
            repo_files={"app.py": b"print('x')\n"},
            registry=_FakeRegistry(
                strategy=_StaticStrategy(chunks_by_file={"app.py": [chunk]})
            ),
            provider=provider,
        )

        self.assertEqual(stats.vectors_upserted, 1)
        self.assertEqual(len(provider.seen_texts), 1)
        self.assertIn("\ufffd", provider.seen_texts[0])

    def test_batcher_validation_propagates_for_oversized_inputs(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files": ["app.py"],
        }
        chunk = _make_chunk(
            repo_slug="demo-repo",
            file_path="app.py",
            content=b"too many tokens here",
        )

        with self.assertRaises(ValueError):
            self._run_index_repo(
                manifest=manifest,
                repo_files={"app.py": b"too many tokens here"},
                registry=_FakeRegistry(
                    strategy=_StaticStrategy(chunks_by_file={"app.py": [chunk]})
                ),
                embedding_config=EmbeddingConfig(
                    model="dummy-model", batch_size=2, max_tokens=2
                ),
                token_counter=lambda text, model: 5,
            )

    def test_chunking_errors_propagate(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files": ["app.py"],
        }
        strategy = _StaticStrategy(
            errors_by_file={"app.py": RuntimeError("chunking failed")}
        )

        with self.assertRaisesRegex(RuntimeError, "chunking failed"):
            self._run_index_repo(
                manifest=manifest,
                repo_files={"app.py": b"print('x')\n"},
                registry=_FakeRegistry(strategy=strategy),
            )

    def test_embedding_provider_errors_propagate(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files": ["app.py"],
        }
        strategy = _StaticStrategy(
            chunks_by_file={
                "app.py": [
                    _make_chunk(
                        repo_slug="demo-repo",
                        file_path="app.py",
                        content=b"print('x')\n",
                    )
                ]
            }
        )

        with self.assertRaisesRegex(RuntimeError, "embedding failed"):
            self._run_index_repo(
                manifest=manifest,
                repo_files={"app.py": b"print('x')\n"},
                registry=_FakeRegistry(strategy=strategy),
                provider=_CapturingProvider(error=RuntimeError("embedding failed")),
            )

    def test_vector_store_errors_propagate(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files": ["app.py"],
        }
        strategy = _StaticStrategy(
            chunks_by_file={
                "app.py": [
                    _make_chunk(
                        repo_slug="demo-repo",
                        file_path="app.py",
                        content=b"print('x')\n",
                    )
                ]
            }
        )

        with self.assertRaisesRegex(RuntimeError, "upsert failed"):
            self._run_index_repo(
                manifest=manifest,
                repo_files={"app.py": b"print('x')\n"},
                registry=_FakeRegistry(strategy=strategy),
                store=_CapturingStore(error=RuntimeError("upsert failed")),
            )

    def test_file_limit_and_size_limit_bound_processed_files(self) -> None:
        manifest = {
            "repo_slug": "demo-repo",
            "head_commit": "abc123",
            "files_with_hashes": [
                {"path": "small.py", "content_hash": "x" * 64, "size_bytes": 8},
                {"path": "large.py", "content_hash": "y" * 64, "size_bytes": 500},
                {"path": "later.py", "content_hash": "z" * 64, "size_bytes": 8},
            ],
        }
        strategy = _StaticStrategy(
            chunks_by_file={
                "small.py": [
                    _make_chunk(
                        repo_slug="demo-repo", file_path="small.py", content=b"print(1)"
                    )
                ],
                "later.py": [
                    _make_chunk(
                        repo_slug="demo-repo", file_path="later.py", content=b"print(2)"
                    )
                ],
            }
        )

        stats, _, _ = self._run_index_repo(
            manifest=manifest,
            repo_files={
                "small.py": b"print(1)",
                "large.py": b"x" * 500,
                "later.py": b"print(2)",
            },
            registry=_FakeRegistry(strategy=strategy),
            max_file_bytes=100,
            file_limit=1,
        )

        self.assertEqual(stats.files_seen, 1)
        self.assertEqual(stats.files_indexed, 1)
        self.assertEqual(stats.vectors_upserted, 1)


if __name__ == "__main__":
    unittest.main()
