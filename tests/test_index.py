import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline.index import index_snapshot


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestIndex(unittest.TestCase):
    def test_index_snapshot_generates_docs_and_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            snapshot = base / "output" / "repoA" / "onboarding_snapshot.json"
            _write_json(
                snapshot,
                {
                    "repo_slug": "repoA",
                    "head_commit": "abc123",
                    "structure_summary": {
                        "total_files": 2,
                        "file_type_counts": [{"extension": ".py", "count": 2}],
                        "start_here_candidates": [{"path": "README.md", "score": 100, "reasons": ["project_overview"]}],
                    },
                    "hotspots": [{"path": "src/app.py", "touch_count": 3, "last_touched": "2026-01-01T00:00:00+00:00"}],
                },
            )
            index_root = base / "index"

            docs_path = index_snapshot(snapshot, index_root=index_root, max_hotspots=10)
            self.assertTrue(docs_path.exists())
            lines = docs_path.read_text(encoding="utf-8").splitlines()
            self.assertGreaterEqual(len(lines), 3)

            metadata = json.loads((index_root / "repoA" / "abc123" / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["repo_slug"], "repoA")
            self.assertEqual(metadata["head_commit"], "abc123")

            registry = json.loads((index_root / "index_registry.json").read_text(encoding="utf-8"))
            self.assertEqual(len(registry["entries"]), 1)
            self.assertEqual(registry["entries"][0]["repo_slug"], "repoA")

    def test_index_registry_upsert_by_version_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            snapshot = base / "output" / "repoA" / "onboarding_snapshot.json"
            _write_json(
                snapshot,
                {
                    "repo_slug": "repoA",
                    "head_commit": "abc123",
                    "structure_summary": {"total_files": 1, "file_type_counts": [], "start_here_candidates": []},
                    "hotspots": [],
                },
            )
            index_root = base / "index"
            index_snapshot(snapshot, index_root=index_root)
            index_snapshot(snapshot, index_root=index_root)

            registry = json.loads((index_root / "index_registry.json").read_text(encoding="utf-8"))
            self.assertEqual(len(registry["entries"]), 1)


if __name__ == "__main__":
    unittest.main()
