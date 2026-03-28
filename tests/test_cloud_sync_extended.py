"""
Extended tests for cloud_sync.py — validation edge cases, MemorySyncStore
file fingerprint handling, PostgresSyncStore via mocks, and the module-level
sync_cloud_safe function.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.pipeline.cloud_sync import (
    MemorySyncStore,
    PostgresSyncStore,
    _ensure_cloud_safe,
    _extract_file_fingerprints,
    _sanitize_structure_metrics,
    build_cloud_safe_payload,
    is_cloud_sync_enabled,
    sync_cloud_safe,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestEnsureCloudSafe(unittest.TestCase):
    """Tests for _ensure_cloud_safe validation."""

    def test_ensure_cloud_safe_forbidden_key(self) -> None:
        """Top-level forbidden key → ValueError."""
        with self.assertRaises(ValueError):
            _ensure_cloud_safe({"commit_message": "oops"})

    def test_ensure_cloud_safe_nested_forbidden(self) -> None:
        """Forbidden key nested in a dict → ValueError."""
        with self.assertRaises(ValueError):
            _ensure_cloud_safe({"data": {"author_email": "x@y.com"}})

    def test_ensure_cloud_safe_forbidden_in_list(self) -> None:
        """Forbidden key in a dict inside a list → ValueError."""
        with self.assertRaises(ValueError):
            _ensure_cloud_safe({"items": [{"absolute_path": "/etc/passwd"}]})

    def test_ensure_cloud_safe_valid_payload(self) -> None:
        """Valid payload passes without error."""
        _ensure_cloud_safe({"tenant_id": "t1", "data": {"count": 5}})


class TestExtractFileFingerprints(unittest.TestCase):
    """Tests for _extract_file_fingerprints edge cases."""

    def test_ingest_path_missing(self) -> None:
        """source_ingest_path points to non-existent file → empty list."""
        result = _extract_file_fingerprints(
            {"transform_metadata": {"source_ingest_path": "/nonexistent/ingest.json"}},
            tenant_salt="salt",
        )
        self.assertEqual(result, [])

    def test_ingest_path_not_string(self) -> None:
        """source_ingest_path is not a string → empty list."""
        result = _extract_file_fingerprints(
            {"transform_metadata": {"source_ingest_path": 123}},
            tenant_salt="salt",
        )
        self.assertEqual(result, [])

    def test_ingest_path_empty_string(self) -> None:
        """source_ingest_path is empty string → empty list."""
        result = _extract_file_fingerprints(
            {"transform_metadata": {"source_ingest_path": ""}},
            tenant_salt="salt",
        )
        self.assertEqual(result, [])

    def test_files_not_list(self) -> None:
        """files field in ingest.json is not a list → empty list."""
        with tempfile.TemporaryDirectory() as tmp:
            ingest_path = Path(tmp) / "ingest.json"
            _write_json(ingest_path, {"files": "not-a-list"})
            result = _extract_file_fingerprints(
                {"transform_metadata": {"source_ingest_path": str(ingest_path)}},
                tenant_salt="salt",
            )
            self.assertEqual(result, [])

    def test_file_path_not_string(self) -> None:
        """Non-string entry in files list → skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            ingest_path = Path(tmp) / "ingest.json"
            _write_json(ingest_path, {"files": [123, "valid.py"]})
            result = _extract_file_fingerprints(
                {"transform_metadata": {"source_ingest_path": str(ingest_path)}},
                tenant_salt="salt",
            )
            # Only the string entry should produce a fingerprint
            self.assertEqual(len(result), 1)


class TestSanitizeStructureMetrics(unittest.TestCase):
    """Tests for _sanitize_structure_metrics edge cases."""

    def test_entry_not_dict_in_top_levels(self) -> None:
        """Non-dict entry in top_level_directories → skipped."""
        result = _sanitize_structure_metrics(
            {
                "total_files": 5,
                "top_level_directories": ["not-a-dict", {"path": "src", "file_count": 3}],
                "file_type_counts": [],
            },
            tenant_salt="salt",
        )
        # Only the valid dict entry should appear
        self.assertEqual(len(result["top_level_directories"]), 1)

    def test_entry_not_dict_in_file_types(self) -> None:
        """Non-dict entry in file_type_counts → skipped."""
        result = _sanitize_structure_metrics(
            {
                "total_files": 5,
                "top_level_directories": [],
                "file_type_counts": ["not-a-dict", {"extension": ".py", "count": 3}],
            },
            tenant_salt="salt",
        )
        self.assertEqual(len(result["file_type_counts"]), 1)


class TestBuildCloudSafePayload(unittest.TestCase):
    """Tests for build_cloud_safe_payload edge cases."""

    def test_hotspot_not_dict(self) -> None:
        """Non-dict entry in hotspots → skipped in hotspot_metrics."""
        with tempfile.TemporaryDirectory() as tmp:
            transform_path = Path(tmp) / "transform.json"
            _write_json(
                transform_path,
                {
                    "repo_slug": "repoA",
                    "repo_url": "https://example.com/repoA",
                    "head_commit": "abc123",
                    "structure_summary": {
                        "total_files": 0,
                        "top_level_directories": [],
                        "file_type_counts": [],
                    },
                    "hotspots": ["not-a-dict", {"path": "a.py", "touch_count": 5, "last_touched": "2026-01-01"}],
                    "transform_metadata": {},
                },
            )
            payload = build_cloud_safe_payload(
                transform_path, "tenantA", "userA", "saltA"
            )
            # Only the valid dict hotspot should appear
            self.assertEqual(len(payload["hotspot_metrics"]), 1)


class TestMemorySyncStoreFileFingerprints(unittest.TestCase):
    """Tests for MemorySyncStore file fingerprint handling."""

    def test_memory_store_processes_file_fingerprints(self) -> None:
        """File fingerprints in payload → stored in version_files."""
        store = MemorySyncStore()
        payload = {
            "tenant_id": "t1",
            "repo_fingerprint": "rf1",
            "canonical_repo_ref_hash": "crh1",
            "head_commit": "abc",
            "version_key": "vk1",
            "structure_metrics": {"total_files": 1},
            "hotspot_metrics": [],
            "file_fingerprints": [
                {"file_path_hash": "fph1", "content_hash": "ch1"},
                {"file_path_hash": "fph2", "content_hash": None},
            ],
            "sync_metadata": {
                "user_id": "u1",
                "local_run_id": "lr1",
                "synced_at": "2026-01-01T00:00:00Z",
                "schema_version": 1,
            },
        }
        result = store.sync_cloud_safe(payload)
        self.assertEqual(result.status, "success")
        self.assertEqual(len(store.version_files), 2)
        self.assertIn(("vk1", "fph1"), store.version_files)
        self.assertIn(("vk1", "fph2"), store.version_files)


class TestPostgresSyncStore(unittest.TestCase):
    """Tests for PostgresSyncStore using mocks (no real Postgres needed)."""

    def test_connect_no_psycopg(self) -> None:
        """Missing psycopg → RuntimeError."""
        store = PostgresSyncStore("postgresql://localhost/test")
        with patch.dict("sys.modules", {"psycopg": None}):
            with self.assertRaises(RuntimeError) as ctx:
                store._connect()
            self.assertIn("psycopg", str(ctx.exception))

    def test_connect_with_psycopg(self) -> None:
        """psycopg available → calls psycopg.connect (line 261)."""
        store = PostgresSyncStore("postgresql://localhost/test")
        mock_psycopg = MagicMock()
        mock_psycopg.connect.return_value = MagicMock()
        with patch.dict("sys.modules", {"psycopg": mock_psycopg}):
            conn = store._connect()
        mock_psycopg.connect.assert_called_once_with("postgresql://localhost/test")
        self.assertIsNotNone(conn)

    def test_apply_schema(self) -> None:
        """apply_schema reads SQL file and executes it."""
        with tempfile.TemporaryDirectory() as tmp:
            sql_path = Path(tmp) / "schema.sql"
            sql_path.write_text("CREATE TABLE test (id INT);", encoding="utf-8")

            store = PostgresSyncStore("postgresql://localhost/test")
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            with patch.object(store, "_connect", return_value=mock_conn):
                store.apply_schema(sql_path)
            mock_cursor.execute.assert_called_once_with("CREATE TABLE test (id INT);")

    def test_sync_cloud_safe_full(self) -> None:
        """Full sync through PostgresSyncStore with mocked connection."""
        store = PostgresSyncStore("postgresql://localhost/test")
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # fetchone returns (repo_id,) and (version_id,)
        mock_cursor.fetchone.side_effect = [(1,), (1,)]
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        payload = {
            "tenant_id": "t1",
            "repo_fingerprint": "rf1",
            "canonical_repo_ref_hash": "crh1",
            "head_commit": "abc",
            "version_key": "vk1",
            "structure_metrics": {"total_files": 1},
            "hotspot_metrics": [
                {"file_hash": "fh1", "touch_count": 3, "last_touched": "2026-01-01"},
            ],
            "file_fingerprints": [
                {"file_path_hash": "fph1", "content_hash": "ch1"},
            ],
            "sync_metadata": {
                "user_id": "u1",
                "local_run_id": "lr1",
                "synced_at": "2026-01-01T00:00:00Z",
                "schema_version": 1,
            },
        }

        with patch.object(store, "_connect", return_value=mock_conn):
            result = store.sync_cloud_safe(payload)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.version_key, "vk1")
        # Should have executed: tenant INSERT, repo INSERT, version INSERT,
        # hotspot INSERT, file INSERT, sync_run INSERT = 6 calls
        self.assertEqual(mock_cursor.execute.call_count, 6)


class TestSyncCloudSafeFunction(unittest.TestCase):
    """Tests for the module-level sync_cloud_safe function."""

    def test_sync_cloud_safe_builds_and_delegates(self) -> None:
        """sync_cloud_safe builds payload and delegates to PostgresSyncStore."""
        with tempfile.TemporaryDirectory() as tmp:
            transform_path = Path(tmp) / "transform.json"
            _write_json(
                transform_path,
                {
                    "repo_slug": "repoA",
                    "repo_url": "https://example.com/repoA",
                    "head_commit": "abc",
                    "structure_summary": {
                        "total_files": 0,
                        "top_level_directories": [],
                        "file_type_counts": [],
                    },
                    "hotspots": [],
                    "transform_metadata": {},
                },
            )
            mock_result = MagicMock()
            mock_result.status = "success"
            mock_result.version_key = "vk1"
            mock_result.synced_at = "2026-01-01"

            with patch(
                "src.pipeline.cloud_sync.PostgresSyncStore"
            ) as MockStore:
                mock_store_instance = MagicMock()
                mock_store_instance.sync_cloud_safe.return_value = mock_result
                MockStore.return_value = mock_store_instance

                result = sync_cloud_safe(
                    transform_json_path=transform_path,
                    tenant_id="t1",
                    user_id="u1",
                    tenant_salt="salt",
                    db_url="postgresql://localhost/test",
                )
            self.assertEqual(result.status, "success")
            mock_store_instance.sync_cloud_safe.assert_called_once()

    def test_sync_cloud_safe_with_apply_schema(self) -> None:
        """sync_cloud_safe calls apply_schema when flag is set."""
        with tempfile.TemporaryDirectory() as tmp:
            transform_path = Path(tmp) / "transform.json"
            schema_path = Path(tmp) / "schema.sql"
            schema_path.write_text("CREATE TABLE t (id INT);", encoding="utf-8")
            _write_json(
                transform_path,
                {
                    "repo_slug": "repoA",
                    "repo_url": "https://example.com/repoA",
                    "head_commit": "abc",
                    "structure_summary": {
                        "total_files": 0,
                        "top_level_directories": [],
                        "file_type_counts": [],
                    },
                    "hotspots": [],
                    "transform_metadata": {},
                },
            )
            mock_result = MagicMock()
            mock_result.status = "success"

            with patch(
                "src.pipeline.cloud_sync.PostgresSyncStore"
            ) as MockStore:
                mock_store_instance = MagicMock()
                mock_store_instance.sync_cloud_safe.return_value = mock_result
                MockStore.return_value = mock_store_instance

                sync_cloud_safe(
                    transform_json_path=transform_path,
                    tenant_id="t1",
                    user_id="u1",
                    tenant_salt="salt",
                    db_url="postgresql://localhost/test",
                    schema_sql_path=schema_path,
                    apply_schema=True,
                )
            mock_store_instance.apply_schema.assert_called_once_with(schema_path)


class TestIsCloudSyncEnabled(unittest.TestCase):
    """Tests for is_cloud_sync_enabled."""

    def test_true_values(self) -> None:
        """Various truthy flag values → True."""
        for val in ("1", "true", "True", "TRUE", "yes", "on", " true "):
            self.assertTrue(is_cloud_sync_enabled(val), f"Expected True for {val!r}")

    def test_false_values(self) -> None:
        """Various falsy flag values → False."""
        for val in ("0", "false", "False", "no", "off", ""):
            self.assertFalse(is_cloud_sync_enabled(val), f"Expected False for {val!r}")

    def test_reads_from_env(self) -> None:
        """When flag is None, reads from ENABLE_CLOUD_SYNC env var."""
        with patch.dict(os.environ, {"ENABLE_CLOUD_SYNC": "true"}):
            self.assertTrue(is_cloud_sync_enabled())

    def test_default_false_when_env_missing(self) -> None:
        """When flag is None and env var not set, defaults to false."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_cloud_sync_enabled())


if __name__ == "__main__":
    unittest.main()
