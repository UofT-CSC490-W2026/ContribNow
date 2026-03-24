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
    """
    Create a multi-commit git repo that exercises all gold-layer features:
      - src/app.py and src/utils.py co-change >= 3 times (hits threshold)
      - src/app.py imports from src.utils (dependency graph)
      - pytest.ini present (convention detection)
      - Multiple commits per file (hotspots, authorship)
    """
    _run(["git", "init"], cwd=repo_dir)
    _run(["git", "config", "user.name", "Test User"], cwd=repo_dir)
    _run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir)

    # Commit 1: bootstrap
    _write(repo_dir / "README.md", "# Demo repo\n")
    _write(repo_dir / "src" / "app.py", "print('v1')\n")
    _run(["git", "add", "."], cwd=repo_dir)
    _run(["git", "commit", "-m", "initial commit"], cwd=repo_dir)

    # Commit 2: add utils, app imports it
    _write(repo_dir / "src" / "app.py", "from src.utils import util\nprint(util())\n")
    _write(repo_dir / "src" / "utils.py", "def util():\n    return 1\n")
    _run(["git", "add", "."], cwd=repo_dir)
    _run(["git", "commit", "-m", "add utils"], cwd=repo_dir)

    # Commit 3: add pytest config, update app
    _write(repo_dir / "pytest.ini", "[pytest]\ntestpaths = tests\n")
    _write(repo_dir / "src" / "app.py", "from src.utils import util\nprint(util() + 1)\n")
    _run(["git", "add", "."], cwd=repo_dir)
    _run(["git", "commit", "-m", "add pytest config"], cwd=repo_dir)

    # Commit 4: co-change app + utils (count = 2)
    _write(repo_dir / "src" / "app.py", "from src.utils import util\nresult = util() + 2\n")
    _write(repo_dir / "src" / "utils.py", "def util():\n    return 2\n")
    _run(["git", "add", "."], cwd=repo_dir)
    _run(["git", "commit", "-m", "bump util return value"], cwd=repo_dir)

    # Commit 5: co-change app + utils (count = 3 — hits threshold)
    _write(repo_dir / "src" / "app.py", "from src.utils import util\nresult = util() + 3\n")
    _write(repo_dir / "src" / "utils.py", "def util():\n    return 3\n")
    _run(["git", "add", "."], cwd=repo_dir)
    _run(["git", "commit", "-m", "final bump"], cwd=repo_dir)


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

            # Existing fields
            self.assertIn("structure_summary", transform_payload)
            self.assertIn("hotspots", transform_payload)
            self.assertTrue(
                any(item["path"] == "src/app.py" and item["touch_count"] >= 2 for item in transform_payload["hotspots"])
            )

            # New gold-layer fields all present
            self.assertIn("co_change_pairs", transform_payload)
            self.assertIn("risk_levels", transform_payload)
            self.assertIn("authorship", transform_payload)
            self.assertIn("dependency_graph", transform_payload)
            self.assertIn("conventions", transform_payload)

            snapshot_path = load_artifact(transform_path, output_root)
            self.assertTrue(snapshot_path.exists())
            index_payload = json.loads((output_root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index_payload["artifacts"]), 1)
            self.assertEqual(index_payload["artifacts"][0]["repo_slug"], transform_payload["repo_slug"])

    def test_ingest_schema_v2_fields(self) -> None:
        """Ingest schema v2 includes author info, per-file changes, and content hashes."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_repo = base / "source-repo"
            source_repo.mkdir(parents=True, exist_ok=True)
            _create_git_repo(source_repo)

            raw_root = base / "raw"
            ingested = ingest_repos([source_repo.resolve().as_uri()], raw_root=raw_root)
            payload = json.loads((ingested[0] / "ingest.json").read_text(encoding="utf-8"))

            # Schema version
            self.assertEqual(payload.get("ingest_schema_version"), 2)

            # files_with_hashes present and matches flat files list length
            self.assertIn("files_with_hashes", payload)
            self.assertEqual(len(payload["files_with_hashes"]), len(payload["files"]))
            first_entry = payload["files_with_hashes"][0]
            self.assertIn("path", first_entry)
            self.assertIn("content_hash", first_entry)
            self.assertIn("size_bytes", first_entry)
            self.assertTrue(all(len(e["content_hash"]) == 64 for e in payload["files_with_hashes"]))

            # Commit log now has author name/email and files_changed list
            first_commit = payload["commit_log"][0]
            self.assertIn("author_name", first_commit)
            self.assertIn("author_email", first_commit)
            self.assertIn("files_changed", first_commit)
            self.assertIsInstance(first_commit["files_changed"], list)
            self.assertNotIn("files_changed_count", first_commit)

    def test_co_change_matrix_threshold(self) -> None:
        """src/app.py and src/utils.py co-change >= 3 times — should appear in result."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_repo = base / "source-repo"
            source_repo.mkdir(parents=True, exist_ok=True)
            _create_git_repo(source_repo)

            raw_root = base / "raw"
            transformed_root = base / "transform"
            ingested = ingest_repos([source_repo.resolve().as_uri()], raw_root=raw_root)
            transform_path = transform_repo(ingested[0], transformed_root)
            payload = json.loads(transform_path.read_text(encoding="utf-8"))

            co_change_pairs = payload["co_change_pairs"]
            self.assertIsInstance(co_change_pairs, list)

            # app.py and utils.py must appear together
            found = any(
                (p["file_a"] == "src/app.py" and p["file_b"] == "src/utils.py")
                or (p["file_a"] == "src/utils.py" and p["file_b"] == "src/app.py")
                for p in co_change_pairs
            )
            self.assertTrue(found, f"Expected src/app.py ↔ src/utils.py in co_change_pairs. Got: {co_change_pairs}")

            # Count must be >= 3 (our threshold)
            pair = next(
                p for p in co_change_pairs
                if "src/app.py" in (p["file_a"], p["file_b"])
                and "src/utils.py" in (p["file_a"], p["file_b"])
            )
            self.assertGreaterEqual(pair["co_change_count"], 3)

    def test_risk_levels_present_and_valid(self) -> None:
        """Every risk_level entry has required fields and a valid level value."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_repo = base / "source-repo"
            source_repo.mkdir(parents=True, exist_ok=True)
            _create_git_repo(source_repo)

            raw_root = base / "raw"
            transformed_root = base / "transform"
            ingested = ingest_repos([source_repo.resolve().as_uri()], raw_root=raw_root)
            transform_path = transform_repo(ingested[0], transformed_root)
            payload = json.loads(transform_path.read_text(encoding="utf-8"))

            risk_levels = payload["risk_levels"]
            self.assertIsInstance(risk_levels, list)
            self.assertGreater(len(risk_levels), 0)
            valid_levels = {"high", "medium", "low"}
            for entry in risk_levels:
                self.assertIn("path", entry)
                self.assertIn("risk_level", entry)
                self.assertIn(entry["risk_level"], valid_levels)
                self.assertIn("risk_score", entry)
                self.assertIn("factors", entry)

    def test_authorship_per_file(self) -> None:
        """Authorship should attribute commits to Test User for touched files."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_repo = base / "source-repo"
            source_repo.mkdir(parents=True, exist_ok=True)
            _create_git_repo(source_repo)

            raw_root = base / "raw"
            transformed_root = base / "transform"
            ingested = ingest_repos([source_repo.resolve().as_uri()], raw_root=raw_root)
            transform_path = transform_repo(ingested[0], transformed_root)
            payload = json.loads(transform_path.read_text(encoding="utf-8"))

            authorship = payload["authorship"]
            self.assertIsInstance(authorship, list)
            self.assertGreater(len(authorship), 0)

            app_entry = next((a for a in authorship if a["path"] == "src/app.py"), None)
            self.assertIsNotNone(app_entry, "src/app.py should have authorship data")
            self.assertGreaterEqual(app_entry["total_commits"], 2)
            self.assertGreaterEqual(app_entry["distinct_authors"], 1)
            contributors = app_entry["primary_contributors"]
            self.assertTrue(any(c["name"] == "Test User" for c in contributors))

    def test_convention_detection_pytest(self) -> None:
        """pytest.ini in the repo should be detected as test framework."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_repo = base / "source-repo"
            source_repo.mkdir(parents=True, exist_ok=True)
            _create_git_repo(source_repo)  # creates pytest.ini

            raw_root = base / "raw"
            transformed_root = base / "transform"
            ingested = ingest_repos([source_repo.resolve().as_uri()], raw_root=raw_root)
            transform_path = transform_repo(ingested[0], transformed_root)
            payload = json.loads(transform_path.read_text(encoding="utf-8"))

            conventions = payload["conventions"]
            self.assertIsInstance(conventions, dict)
            tf = conventions.get("test_framework")
            self.assertIsNotNone(tf, "test_framework should be detected")
            self.assertEqual(tf["name"], "pytest")

    def test_dependency_graph_python_imports(self) -> None:
        """src/app.py imports from src.utils — should appear in imports_map."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_repo = base / "source-repo"
            source_repo.mkdir(parents=True, exist_ok=True)
            _create_git_repo(source_repo)

            raw_root = base / "raw"
            transformed_root = base / "transform"
            ingested = ingest_repos([source_repo.resolve().as_uri()], raw_root=raw_root)
            transform_path = transform_repo(ingested[0], transformed_root)
            payload = json.loads(transform_path.read_text(encoding="utf-8"))

            dep_graph = payload["dependency_graph"]
            self.assertIn("imports_map", dep_graph)
            self.assertIn("imported_by", dep_graph)

            imports_map = dep_graph["imports_map"]
            self.assertIn("src/app.py", imports_map)
            # app.py does: from src.utils import util
            app_imports = imports_map["src/app.py"]
            self.assertTrue(
                any("src.utils" in imp or "src/utils" in imp for imp in app_imports),
                f"Expected src.utils in app.py imports. Got: {app_imports}",
            )

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
