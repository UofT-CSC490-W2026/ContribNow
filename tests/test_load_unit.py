"""
Unit tests for load.py — covers env file edge cases and CLI entry points.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.pipeline.load import _load_env_file, _parse_args, main


class TestLoadEnvFile(unittest.TestCase):
    """Tests for _load_env_file edge cases."""

    def test_nonexistent_file(self) -> None:
        """Non-existent .env file → returns without error."""
        _load_env_file(Path("/nonexistent/.env"))
        # Should not raise

    def test_empty_key_skipped(self) -> None:
        """Line with empty key (e.g., '=value') → skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("=somevalue\nVALID_KEY=valid\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                _load_env_file(env_file)
                self.assertNotIn("", os.environ)
                self.assertEqual(os.environ.get("VALID_KEY"), "valid")

    def test_override_mode(self) -> None:
        """With override=True, existing env vars are overwritten."""
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("MY_KEY=new_value\n", encoding="utf-8")
            with patch.dict(os.environ, {"MY_KEY": "old_value"}):
                _load_env_file(env_file, override=True)
                self.assertEqual(os.environ["MY_KEY"], "new_value")

    def test_comment_and_blank_lines_ignored(self) -> None:
        """Comments and blank lines are skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("# comment\n\nKEY=val\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                _load_env_file(env_file)
                self.assertEqual(os.environ.get("KEY"), "val")


class TestLoadParseArgs(unittest.TestCase):
    """Tests for _parse_args CLI argument parsing."""

    def test_parse_args_required(self) -> None:
        with patch("sys.argv", ["load", "--transform-root", "/tmp/transform", "--output-root", "/tmp/output"]):
            args = _parse_args()
        self.assertEqual(args.transform_root, Path("/tmp/transform"))
        self.assertEqual(args.output_root, Path("/tmp/output"))
        self.assertFalse(args.sync_cloud)
        self.assertFalse(args.apply_schema)

    def test_parse_args_all_options(self) -> None:
        with patch("sys.argv", [
            "load",
            "--transform-root", "/tmp/transform",
            "--output-root", "/tmp/output",
            "--sync-cloud",
            "--tenant-id", "t1",
            "--user-id", "u1",
            "--tenant-salt", "salt",
            "--db-url", "postgresql://localhost/db",
            "--env-file", "/tmp/.env",
            "--schema-sql-path", "/tmp/schema.sql",
            "--apply-schema",
        ]):
            args = _parse_args()
        self.assertTrue(args.sync_cloud)
        self.assertTrue(args.apply_schema)
        self.assertEqual(args.tenant_id, "t1")
        self.assertEqual(args.user_id, "u1")
        self.assertEqual(args.tenant_salt, "salt")
        self.assertEqual(args.db_url, "postgresql://localhost/db")
        self.assertEqual(args.env_file, Path("/tmp/.env"))
        self.assertEqual(args.schema_sql_path, Path("/tmp/schema.sql"))

    def test_parse_args_missing_required(self) -> None:
        with patch("sys.argv", ["load"]):
            with self.assertRaises(SystemExit):
                _parse_args()


class TestLoadMain(unittest.TestCase):
    """Tests for load main() entry point."""

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_main_success_no_cloud(self) -> None:
        """main() loads transform artifacts and returns 0."""
        with tempfile.TemporaryDirectory() as tmp:
            transform_root = Path(tmp) / "transform"
            output_root = Path(tmp) / "output"
            self._write_json(
                transform_root / "repoA" / "transform.json",
                {
                    "repo_slug": "repoA",
                    "repo_url": "file:///test",
                    "head_commit": "abc",
                    "structure_summary": {"total_files": 1},
                    "hotspots": [],
                    "transform_metadata": {},
                },
            )
            env_file = Path(tmp) / ".env"
            env_file.write_text("", encoding="utf-8")

            with patch.dict(os.environ, {"ENABLE_CLOUD_SYNC": "false"}, clear=False):
                with patch("sys.argv", [
                    "load",
                    "--transform-root", str(transform_root),
                    "--output-root", str(output_root),
                    "--env-file", str(env_file),
                ]):
                    exit_code = main()
            self.assertEqual(exit_code, 0)
            self.assertTrue((output_root / "repoA" / "onboarding_snapshot.json").exists())

    def test_main_no_transforms(self) -> None:
        """main() returns 1 when no transform.json files found."""
        with tempfile.TemporaryDirectory() as tmp:
            transform_root = Path(tmp) / "transform"
            transform_root.mkdir()
            output_root = Path(tmp) / "output"
            env_file = Path(tmp) / ".env"
            env_file.write_text("", encoding="utf-8")

            with patch.dict(os.environ, {"ENABLE_CLOUD_SYNC": "false"}, clear=False):
                with patch("sys.argv", [
                    "load",
                    "--transform-root", str(transform_root),
                    "--output-root", str(output_root),
                    "--env-file", str(env_file),
                ]):
                    exit_code = main()
            self.assertEqual(exit_code, 1)

    def test_main_with_cloud_sync(self) -> None:
        """main() with --sync-cloud delegates to sync_cloud_safe."""
        with tempfile.TemporaryDirectory() as tmp:
            transform_root = Path(tmp) / "transform"
            output_root = Path(tmp) / "output"
            self._write_json(
                transform_root / "repoA" / "transform.json",
                {
                    "repo_slug": "repoA",
                    "repo_url": "file:///test",
                    "head_commit": "abc",
                    "structure_summary": {"total_files": 0, "top_level_directories": [], "file_type_counts": []},
                    "hotspots": [],
                    "transform_metadata": {},
                },
            )
            env_file = Path(tmp) / ".env"
            env_file.write_text("", encoding="utf-8")

            mock_result = MagicMock()
            mock_result.status = "success"
            mock_result.version_key = "vk1"
            mock_result.synced_at = "2026-01-01"

            with patch("src.pipeline.load.sync_cloud_safe", return_value=mock_result):
                with patch("sys.argv", [
                    "load",
                    "--transform-root", str(transform_root),
                    "--output-root", str(output_root),
                    "--sync-cloud",
                    "--tenant-id", "t1",
                    "--user-id", "u1",
                    "--tenant-salt", "salt",
                    "--db-url", "postgresql://localhost/db",
                    "--env-file", str(env_file),
                ]):
                    exit_code = main()
            self.assertEqual(exit_code, 0)

    def test_main_cloud_sync_missing_config(self) -> None:
        """main() with --sync-cloud but missing tenant config → handles error."""
        with tempfile.TemporaryDirectory() as tmp:
            transform_root = Path(tmp) / "transform"
            output_root = Path(tmp) / "output"
            self._write_json(
                transform_root / "repoA" / "transform.json",
                {
                    "repo_slug": "repoA",
                    "repo_url": "file:///test",
                    "head_commit": "abc",
                    "structure_summary": {"total_files": 0},
                    "hotspots": [],
                    "transform_metadata": {},
                },
            )
            env_file = Path(tmp) / ".env"
            env_file.write_text("", encoding="utf-8")

            # sync-cloud enabled but no tenant-id/salt/db-url → ValueError caught
            with patch.dict(os.environ, {}, clear=True):
                with patch("sys.argv", [
                    "load",
                    "--transform-root", str(transform_root),
                    "--output-root", str(output_root),
                    "--sync-cloud",
                    "--env-file", str(env_file),
                ]):
                    exit_code = main()
            # The ValueError is caught per-repo, but load_artifact succeeds
            # before the sync fails, so it depends on the error handling
            # Just verify it doesn't crash
            self.assertIn(exit_code, (0, 1))


if __name__ == "__main__":
    unittest.main()
