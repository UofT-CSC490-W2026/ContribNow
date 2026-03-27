import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.pipeline.chunking import ChunkingConfig
from src.pipeline.embedding import (
    EmbeddingConfig,
    EmbeddingRequest,
    LocalEmbeddingProvider,
)
from src.pipeline.indexing import index_repo_in_memory


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


if __name__ == "__main__":
    unittest.main()
