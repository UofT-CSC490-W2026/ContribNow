import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.pipeline.ingest import ingest_repos
from src.pipeline.load import _load_env_file, load_artifact
from src.pipeline.transform import transform_repo


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, capture_output=True, text=True)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _create_git_repo(repo_dir: Path) -> None:
    _run(["git", "init"], cwd=repo_dir)
    _run(["git", "config", "user.name", "Test User"], cwd=repo_dir)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir)

    _write(repo_dir / "README.md", "# Demo repo\n")
    _write(repo_dir / "src" / "app.py", "print('v1')\n")
    _run(["git", "add", "."], cwd=repo_dir)
    _run(["git", "commit", "-m", "initial commit"], cwd=repo_dir)

    _write(repo_dir / "src" / "app.py", "print('v2')\n")
    _write(repo_dir / "src" / "utils.py", "def util():\n    return 1\n")
    _run(["git", "add", "."], cwd=repo_dir)
    _run(["git", "commit", "-m", "second commit"], cwd=repo_dir)


class TestPipelineETL(unittest.TestCase):
    def test_load_env_file_sets_missing_values_without_overriding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "# sample",
                        "TENANT_ID=tenant-from-env",
                        "USER_ID='user-from-env'",
                        "TENANT_SALT=secret-salt",
                        'CLOUD_DB_URL="postgresql://env-user:env-pass@localhost:5432/contribnow"',
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"TENANT_ID": "already-set"}, clear=True):
                _load_env_file(env_file)
                self.assertEqual(os.environ["TENANT_ID"], "already-set")
                self.assertEqual(os.environ["USER_ID"], "user-from-env")
                self.assertEqual(os.environ["TENANT_SALT"], "secret-salt")
                self.assertEqual(
                    os.environ["CLOUD_DB_URL"],
                    "postgresql://env-user:env-pass@localhost:5432/contribnow",
                )

    def test_end_to_end_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_repo = base / "source-repo"
            source_repo.mkdir(parents=True, exist_ok=True)
            _create_git_repo(source_repo)

            raw_root = base / "raw"
            transformed_root = base / "transform"
            output_root = base / "output"
            repo_url = source_repo.resolve().as_uri()

            ingested = ingest_repos([repo_url], raw_root=raw_root)
            self.assertEqual(len(ingested), 1)

            ingest_payload = json.loads((ingested[0] / "ingest.json").read_text(encoding="utf-8"))
            self.assertIn("repo_slug", ingest_payload)
            self.assertIn("files", ingest_payload)
            self.assertIn("commit_log", ingest_payload)
            self.assertGreaterEqual(len(ingest_payload["files"]), 2)
            self.assertGreaterEqual(len(ingest_payload["commit_log"]), 2)

            transform_path = transform_repo(ingested[0], transformed_root, top_n_hotspots=10)
            transform_payload = json.loads(transform_path.read_text(encoding="utf-8"))
            self.assertIn("structure_summary", transform_payload)
            self.assertIn("hotspots", transform_payload)
            self.assertTrue(
                any(item["path"] == "src/app.py" and item["touch_count"] >= 2 for item in transform_payload["hotspots"])
            )

            snapshot_path = load_artifact(transform_path, output_root)
            self.assertTrue(snapshot_path.exists())
            index_payload = json.loads((output_root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index_payload["artifacts"]), 1)
            self.assertEqual(index_payload["artifacts"][0]["repo_slug"], transform_payload["repo_slug"])

    def test_ingest_failure_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_repo = base / "source-repo"
            source_repo.mkdir(parents=True, exist_ok=True)
            _create_git_repo(source_repo)

            raw_root = base / "raw"
            bad_repo = (base / "does-not-exist").resolve().as_uri()
            good_repo = source_repo.resolve().as_uri()

            ingested = ingest_repos([bad_repo, good_repo], raw_root=raw_root)
            self.assertEqual(len(ingested), 1)
            self.assertTrue((ingested[0] / "ingest.json").exists())

    def test_load_index_updates_existing_repo_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            output_root = base / "output"
            transform_root = base / "transform"
            transform_root.mkdir(parents=True, exist_ok=True)

            transform_path = transform_root / "repoA" / "transform.json"
            transform_path.parent.mkdir(parents=True, exist_ok=True)
            transform_path.write_text(
                json.dumps(
                    {
                        "repo_slug": "repoA",
                        "repo_url": "file:///tmp/repoA",
                        "head_commit": "abc123",
                        "structure_summary": {"total_files": 1},
                        "hotspots": [],
                        "transform_metadata": {},
                    }
                ),
                encoding="utf-8",
            )

            load_artifact(transform_path, output_root)

            transform_path.write_text(
                json.dumps(
                    {
                        "repo_slug": "repoA",
                        "repo_url": "file:///tmp/repoA",
                        "head_commit": "def456",
                        "structure_summary": {"total_files": 2},
                        "hotspots": [{"path": "a.py", "touch_count": 3}],
                        "transform_metadata": {},
                    }
                ),
                encoding="utf-8",
            )
            load_artifact(transform_path, output_root)

            index_payload = json.loads((output_root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index_payload["artifacts"]), 1)
            self.assertEqual(index_payload["artifacts"][0]["repo_slug"], "repoA")


if __name__ == "__main__":
    unittest.main()
