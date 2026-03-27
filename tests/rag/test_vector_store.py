import builtins
import os
import types
import unittest
import uuid
from unittest.mock import patch

import numpy as np

from src.pipeline.vector_store import PgVectorStore, VectorRecord
from src.pipeline.vector_store.in_memory import InMemoryVectorStore, _cosine_similarity


class _FakeCursor:
    # Minimal cursor double used by the unit tests below to capture SQL calls.
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self._rows: list[tuple] = []
        self.rowcount: int = 0

    def execute(self, sql: str, params: object = None) -> None:
        self.calls.append(("execute", sql, params))

    def executemany(self, sql: str, params: object) -> None:
        self.calls.append(("executemany", sql, params))

    def fetchall(self) -> list[tuple]:
        return self._rows

    def set_rows(self, rows: list[tuple]) -> None:
        self._rows = rows

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeConnection:
    # Minimal connection double that tracks commits without requiring Postgres.
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.commit_calls = 0

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commit_calls += 1

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class TestInMemoryVectorStore(unittest.TestCase):
    def test_cosine_similarity_dimension_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            _cosine_similarity(
                np.asarray([1.0, 2.0], dtype=np.float32),
                np.asarray([1.0, 2.0, 3.0], dtype=np.float32),
            )

    def test_cosine_similarity_zero_norm_returns_zero(self) -> None:
        score = _cosine_similarity(
            np.asarray([0.0, 0.0], dtype=np.float32),
            np.asarray([1.0, 1.0], dtype=np.float32),
        )
        self.assertEqual(score, 0.0)

    def test_upsert_overwrites_existing_span(self) -> None:
        store = InMemoryVectorStore()
        first = VectorRecord(
            vector=np.asarray([1.0, 0.0], dtype=np.float32),
            repo_slug="repo",
            head_commit="abc",
            file_path="file.py",
            start_line=1,
            end_line=2,
        )
        updated = VectorRecord(
            vector=np.asarray([0.0, 1.0], dtype=np.float32),
            repo_slug="repo",
            head_commit="abc",
            file_path="file.py",
            start_line=1,
            end_line=2,
        )

        self.assertEqual(store.upsert([first]), 1)
        self.assertEqual(store.upsert([updated]), 1)
        self.assertEqual(len(store._records), 1)
        self.assertTrue(np.allclose(store._records[0].vector, updated.vector))

    def test_delete_by_repo_keeps_other_records(self) -> None:
        store = InMemoryVectorStore()
        store.upsert(
            [
                VectorRecord(
                    vector=np.asarray([1.0, 0.0], dtype=np.float32),
                    repo_slug="repo-a",
                    head_commit="abc",
                    file_path="a.py",
                    start_line=1,
                    end_line=1,
                ),
                VectorRecord(
                    vector=np.asarray([0.0, 1.0], dtype=np.float32),
                    repo_slug="repo-b",
                    head_commit="def",
                    file_path="b.py",
                    start_line=2,
                    end_line=2,
                ),
            ]
        )

        removed = store.delete_by_repo("repo-a")
        self.assertEqual(removed, 1)
        self.assertEqual(len(store._records), 1)
        self.assertEqual(store._records[0].repo_slug, "repo-b")

    def test_search_k_zero_returns_empty(self) -> None:
        store = InMemoryVectorStore()
        results = store.search(np.asarray([1.0, 0.0], dtype=np.float32), k=0)
        self.assertEqual(results, [])

    def test_search_rejects_invalid_query(self) -> None:
        store = InMemoryVectorStore()
        with self.assertRaises(ValueError):
            store.search(np.asarray([], dtype=np.float32), k=1)

    def test_search_filters_apply_all_constraints(self) -> None:
        store = InMemoryVectorStore()
        store.upsert(
            [
                VectorRecord(
                    vector=np.asarray([1.0, 0.0], dtype=np.float32),
                    repo_slug="repo-x",
                    head_commit="good",
                    file_path="good.py",
                    start_line=1,
                    end_line=1,
                ),
                VectorRecord(
                    vector=np.asarray([1.0, 0.0], dtype=np.float32),
                    repo_slug="repo",
                    head_commit="bad",
                    file_path="good.py",
                    start_line=1,
                    end_line=1,
                ),
                VectorRecord(
                    vector=np.asarray([1.0, 0.0], dtype=np.float32),
                    repo_slug="repo",
                    head_commit="good",
                    file_path="bad.py",
                    start_line=1,
                    end_line=1,
                ),
                VectorRecord(
                    vector=np.asarray([0.0, 1.0], dtype=np.float32),
                    repo_slug="repo",
                    head_commit="good",
                    file_path="good.py",
                    start_line=10,
                    end_line=12,
                ),
            ]
        )

        results = store.search(
            np.asarray([0.0, 1.0], dtype=np.float32),
            k=5,
            repo_slug="repo",
            head_commit="good",
            file_path="good.py",
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].repo_slug, "repo")
        self.assertEqual(results[0].head_commit, "good")
        self.assertEqual(results[0].file_path, "good.py")


class TestPgVectorStore(unittest.TestCase):
    def test_name_property(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        self.assertEqual(store.name, "pgvector")

    def test_requires_db_url(self) -> None:
        with self.assertRaises(ValueError):
            PgVectorStore(db_url="", embedding_dimensions=3)

    def test_requires_fixed_dimensions(self) -> None:
        with self.assertRaises(ValueError):
            PgVectorStore(
                db_url="postgresql://user:pass@localhost:5432/contribnow_test",
                embedding_dimensions=0,
            )

    def test_vector_literal_rejects_non_finite_values(self) -> None:
        with self.assertRaises(ValueError):
            PgVectorStore._vector_literal(np.asarray([0.1, np.nan], dtype=np.float32))

    def test_vector_literal_rejects_empty_vector(self) -> None:
        with self.assertRaises(ValueError):
            PgVectorStore._vector_literal(np.asarray([], dtype=np.float32))

    def test_validate_identifier_rejects_empty_and_invalid(self) -> None:
        with self.assertRaises(ValueError):
            PgVectorStore._validate_identifier("schema_name", " ")
        with self.assertRaises(ValueError):
            PgVectorStore._validate_identifier("schema_name", "bad-name")

    def test_validate_dimensions_rejects_non_1d(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        with self.assertRaises(ValueError):
            store._validate_dimensions(np.asarray([[1.0, 2.0, 3.0]], dtype=np.float32))

    def test_connect_requires_psycopg(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        original_import = builtins.__import__

        def raising_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "psycopg":
                raise ImportError("no psycopg")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=raising_import):
            with self.assertRaises(RuntimeError):
                store._connect()

    def test_connect_uses_psycopg_connect(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        sentinel = object()
        fake_psycopg = types.SimpleNamespace(
            connect=lambda url: sentinel if url == store.db_url else None
        )

        with patch.dict("sys.modules", {"psycopg": fake_psycopg}):
            conn = store._connect()

        self.assertIs(conn, sentinel)

    def test_ensure_schema_executes_extension_and_table_sql(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            schema_name="public",
            table_name="rag_vectors_test",
            embedding_dimensions=3,
        )
        fake_cursor = _FakeCursor()
        fake_conn = _FakeConnection(fake_cursor)

        with patch.object(store, "_connect", return_value=fake_conn):
            store.ensure_schema()

        statements = [call[1] for call in fake_cursor.calls if call[0] == "execute"]
        self.assertTrue(
            any("CREATE EXTENSION IF NOT EXISTS vector" in sql for sql in statements)
        )
        self.assertTrue(
            any(
                "CREATE TABLE IF NOT EXISTS public.rag_vectors_test" in sql
                for sql in statements
            )
        )
        self.assertTrue(
            any(
                "PRIMARY KEY (repo_slug, head_commit, file_path, start_line, end_line)"
                for sql in statements
            )
        )
        self.assertEqual(fake_conn.commit_calls, 1)

    def test_upsert_uses_executemany(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            table_name="rag_vectors_test",
            embedding_dimensions=3,
        )
        fake_cursor = _FakeCursor()
        fake_conn = _FakeConnection(fake_cursor)

        records = [
            VectorRecord(
                vector=np.asarray([0.1, 0.2, 0.3], dtype=np.float32),
                repo_slug="repo",
                head_commit="abc123",
                file_path="a.py",
                start_line=1,
                end_line=10,
            ),
            VectorRecord(
                vector=np.asarray([0.4, 0.5, 0.6], dtype=np.float32),
                repo_slug="repo",
                head_commit="abc123",
                file_path="b.py",
                start_line=1,
                end_line=8,
            ),
        ]

        with patch.object(store, "_connect", return_value=fake_conn):
            upserted = store.upsert(records)

        self.assertEqual(upserted, 2)
        self.assertEqual(fake_conn.commit_calls, 1)
        executemany_calls = [
            call for call in fake_cursor.calls if call[0] == "executemany"
        ]
        self.assertEqual(len(executemany_calls), 1)
        _, sql, params = executemany_calls[0]
        self.assertIn(
            "ON CONFLICT (repo_slug, head_commit, file_path, start_line, end_line)",
            sql,
        )
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0][0], "repo")
        self.assertEqual(params[0][1], "abc123")
        self.assertEqual(params[0][2], "a.py")
        self.assertEqual(params[0][3], 1)
        self.assertEqual(params[0][4], 10)

    def test_upsert_empty_returns_zero(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        self.assertEqual(store.upsert([]), 0)

    def test_upsert_rejects_dimension_mismatch(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        bad_record = VectorRecord(
            vector=np.asarray([0.1, 0.2], dtype=np.float32),
            repo_slug="repo",
            head_commit="abc123",
            file_path="bad.py",
            start_line=1,
            end_line=1,
        )
        with self.assertRaises(ValueError):
            store.upsert([bad_record])

    def test_search_returns_ranked_results(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            table_name="rag_vectors_test",
            embedding_dimensions=3,
        )
        fake_cursor = _FakeCursor()
        fake_cursor.set_rows(
            [
                ("repo", "abc123", "a.py", 1, 10, 0.01),
                ("repo", "abc123", "b.py", 1, 8, 0.08),
            ]
        )
        fake_conn = _FakeConnection(fake_cursor)

        with patch.object(store, "_connect", return_value=fake_conn):
            results = store.search(
                query_vector=np.asarray([0.1, 0.2, 0.3], dtype=np.float32),
                k=2,
                repo_slug="repo",
                head_commit="abc123",
            )

        self.assertEqual(len(results), 2)
        self.assertGreater(results[0].score, results[1].score)
        self.assertEqual(results[0].head_commit, "abc123")
        self.assertEqual(results[0].file_path, "a.py")

        execute_calls = [call for call in fake_cursor.calls if call[0] == "execute"]
        self.assertEqual(len(execute_calls), 1)
        _, sql, params = execute_calls[0]
        self.assertIn("repo_slug = %s", sql)
        self.assertIn("head_commit = %s", sql)
        self.assertEqual(params[-1], 2)

    def test_search_k_zero_returns_empty(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        results = store.search(np.asarray([0.1, 0.2, 0.3], dtype=np.float32), k=0)
        self.assertEqual(results, [])

    def test_search_with_file_path_filter(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            table_name="rag_vectors_test",
            embedding_dimensions=3,
        )
        fake_cursor = _FakeCursor()
        fake_cursor.set_rows([])
        fake_conn = _FakeConnection(fake_cursor)

        with patch.object(store, "_connect", return_value=fake_conn):
            results = store.search(
                query_vector=np.asarray([0.1, 0.2, 0.3], dtype=np.float32),
                k=5,
                file_path="src/app.py",
            )

        self.assertEqual(results, [])
        execute_calls = [call for call in fake_cursor.calls if call[0] == "execute"]
        self.assertEqual(len(execute_calls), 1)
        _, sql, params = execute_calls[0]
        self.assertIn("file_path = %s", sql)
        self.assertEqual(params[-1], 5)

    def test_search_rejects_dimension_mismatch(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        with self.assertRaises(ValueError):
            store.search(np.asarray([0.1, 0.2], dtype=np.float32), k=3)

    def test_delete_by_repo(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            table_name="rag_vectors_test",
            embedding_dimensions=3,
        )
        fake_cursor = _FakeCursor()
        fake_cursor.rowcount = 2
        fake_conn = _FakeConnection(fake_cursor)

        with patch.object(store, "_connect", return_value=fake_conn):
            deleted = store.delete_by_repo("repo")

        self.assertEqual(deleted, 2)
        self.assertEqual(fake_conn.commit_calls, 1)
        execute_calls = [call for call in fake_cursor.calls if call[0] == "execute"]
        _, sql, params = execute_calls[0]
        self.assertIn("DELETE FROM public.rag_vectors_test", sql)
        self.assertEqual(params[0], "repo")

    def test_delete_by_repo_empty_returns_zero(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        self.assertEqual(store.delete_by_repo(""), 0)

    @unittest.skipUnless(
        os.getenv("RUN_PG_VECTOR_TESTS") == "1",
        "Set RUN_PG_VECTOR_TESTS=1 and PGVECTOR_TEST_DB_URL, or use bash scripts/run_pgvector_tests.sh",
    )
    def test_live_round_trip(self) -> None:
        db_url = os.getenv("PGVECTOR_TEST_DB_URL")
        if not db_url:
            self.skipTest("PGVECTOR_TEST_DB_URL is required")

        # Use a unique table so repeated local runs do not interfere with each other.
        table_name = f"rag_vectors_it_{uuid.uuid4().hex[:8]}"
        store = PgVectorStore(
            db_url=db_url, table_name=table_name, embedding_dimensions=3
        )
        store.ensure_schema()

        try:
            store.upsert(
                [
                    VectorRecord(
                        vector=np.asarray([0.9, 0.1, 0.0], dtype=np.float32),
                        repo_slug="repo",
                        head_commit="abc123",
                        file_path="src/app.py",
                        start_line=1,
                        end_line=1,
                    ),
                    VectorRecord(
                        vector=np.asarray([0.1, 0.9, 0.0], dtype=np.float32),
                        repo_slug="repo",
                        head_commit="abc123",
                        file_path="src/lib.py",
                        start_line=1,
                        end_line=1,
                    ),
                ]
            )
            # Query should rank the first vector higher for this input direction.
            results = store.search(
                query_vector=np.asarray([0.85, 0.15, 0.0], dtype=np.float32),
                k=1,
                repo_slug="repo",
                head_commit="abc123",
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].head_commit, "abc123")
            self.assertEqual(results[0].file_path, "src/app.py")
        finally:
            # Drop the temporary table so the external database stays clean.
            with store._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {store._table_ref}")
                conn.commit()


if __name__ == "__main__":
    unittest.main()
