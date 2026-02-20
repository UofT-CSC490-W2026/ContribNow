import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline.cloud_sync import MemorySyncStore, build_cloud_safe_payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestCloudSync(unittest.TestCase):
    def test_projection_redaction_and_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            ingest_path = base / "raw" / "repoA" / "ingest.json"
            _write_json(
                ingest_path,
                {
                    "repo_slug": "repoA",
                    "files": ["README.md", "src/app.py"],
                    "commit_log": [{"message": "sensitive", "author_email": "secret@example.com"}],
                },
            )

            transform_path = base / "transform" / "repoA" / "transform.json"
            _write_json(
                transform_path,
                {
                    "repo_slug": "repoA",
                    "repo_url": "https://example.com/org/repoA.git",
                    "head_commit": "abc123",
                    "structure_summary": {
                        "total_files": 2,
                        "top_level_directories": [{"path": "src", "file_count": 1}],
                        "file_type_counts": [{"extension": ".py", "count": 1}],
                    },
                    "hotspots": [{"path": "src/app.py", "touch_count": 3, "last_touched": "2026-01-01T00:00:00+00:00"}],
                    "transform_metadata": {"source_ingest_path": str(ingest_path)},
                },
            )

            payload = build_cloud_safe_payload(
                transform_json_path=transform_path,
                tenant_id="tenantA",
                user_id="userA",
                tenant_salt="saltA",
                local_run_id="runA",
            )

            self.assertIn("repo_fingerprint", payload)
            self.assertIn("version_key", payload)
            self.assertEqual(payload["sync_metadata"]["local_run_id"], "runA")
            self.assertEqual(len(payload["file_fingerprints"]), 2)

            as_text = json.dumps(payload)
            self.assertNotIn("src/app.py", as_text)
            self.assertNotIn("secret@example.com", as_text)
            self.assertNotIn("sensitive", as_text)
            self.assertNotIn('"path": "src"', as_text)
            self.assertIn("dir_hash", as_text)

    def test_version_key_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            transform_path = base / "transform.json"
            _write_json(
                transform_path,
                {
                    "repo_slug": "repoA",
                    "repo_url": "https://example.com/org/repoA.git",
                    "head_commit": "abc123",
                    "structure_summary": {"total_files": 0, "top_level_directories": [], "file_type_counts": []},
                    "hotspots": [],
                    "transform_metadata": {},
                },
            )

            p1 = build_cloud_safe_payload(transform_path, "tenantA", "userA", "saltA", local_run_id="run1")
            p2 = build_cloud_safe_payload(transform_path, "tenantA", "userB", "saltA", local_run_id="run2")
            self.assertEqual(p1["version_key"], p2["version_key"])
            self.assertEqual(p1["repo_fingerprint"], p2["repo_fingerprint"])

    def test_hash_stability_for_canonical_repo_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            t1 = base / "t1.json"
            t2 = base / "t2.json"
            common = {
                "repo_slug": "repoA",
                "head_commit": "abc123",
                "structure_summary": {"total_files": 0, "top_level_directories": [], "file_type_counts": []},
                "hotspots": [],
                "transform_metadata": {},
            }
            _write_json(t1, {**common, "repo_url": "HTTPS://EXAMPLE.COM/ORG/REPOA.GIT/"})
            _write_json(t2, {**common, "repo_url": "https://example.com/org/repoa.git"})

            p1 = build_cloud_safe_payload(t1, "tenantA", "userA", "saltA")
            p2 = build_cloud_safe_payload(t2, "tenantA", "userA", "saltA")
            self.assertEqual(p1["repo_fingerprint"], p2["repo_fingerprint"])

    def test_sync_idempotency_with_memory_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            transform_path = base / "transform.json"
            _write_json(
                transform_path,
                {
                    "repo_slug": "repoA",
                    "repo_url": "https://example.com/org/repoA.git",
                    "head_commit": "abc123",
                    "structure_summary": {
                        "total_files": 1,
                        "top_level_directories": [{"path": "src", "file_count": 1}],
                        "file_type_counts": [{"extension": ".py", "count": 1}],
                    },
                    "hotspots": [{"path": "src/app.py", "touch_count": 2, "last_touched": "2026-01-01T00:00:00+00:00"}],
                    "transform_metadata": {},
                },
            )
            payload = build_cloud_safe_payload(transform_path, "tenantA", "userA", "saltA")
            store = MemorySyncStore()

            store.sync_cloud_safe(payload)
            store.sync_cloud_safe(payload)

            self.assertEqual(len(store.tenants), 1)
            self.assertEqual(len(store.repos), 1)
            self.assertEqual(len(store.versions), 1)
            self.assertEqual(len(store.version_hotspots), 1)


if __name__ == "__main__":
    unittest.main()
