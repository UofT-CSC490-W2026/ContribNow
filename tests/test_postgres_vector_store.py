import os
import unittest
import uuid
from unittest.mock import patch

import numpy as np

from src.pipeline.vector_store import PgVectorStore, VectorRecord


class _FakeCursor:
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


class TestPgVectorStore(unittest.TestCase):
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
                "PRIMARY KEY (repo_slug, file_path, start_line, end_line)" in sql
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
                file_path="a.py",
                start_line=1,
                end_line=10,
            ),
            VectorRecord(
                vector=np.asarray([0.4, 0.5, 0.6], dtype=np.float32),
                repo_slug="repo",
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
        self.assertIn("ON CONFLICT (repo_slug, file_path, start_line, end_line)", sql)
        self.assertEqual(len(params), 2)
        self.assertEqual(params[0][0], "repo")
        self.assertEqual(params[0][1], "a.py")
        self.assertEqual(params[0][2], 1)
        self.assertEqual(params[0][3], 10)

    def test_upsert_rejects_dimension_mismatch(self) -> None:
        store = PgVectorStore(
            db_url="postgresql://user:pass@localhost:5432/contribnow_test",
            embedding_dimensions=3,
        )
        bad_record = VectorRecord(
            vector=np.asarray([0.1, 0.2], dtype=np.float32),
            repo_slug="repo",
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
                ("repo", "a.py", 1, 10, 0.01),
                ("repo", "b.py", 1, 8, 0.08),
            ]
        )
        fake_conn = _FakeConnection(fake_cursor)

        with patch.object(store, "_connect", return_value=fake_conn):
            results = store.search(
                query_vector=np.asarray([0.1, 0.2, 0.3], dtype=np.float32),
                k=2,
                repo_slug="repo",
            )

        self.assertEqual(len(results), 2)
        self.assertGreater(results[0].score, results[1].score)
        self.assertEqual(results[0].file_path, "a.py")

        execute_calls = [call for call in fake_cursor.calls if call[0] == "execute"]
        self.assertEqual(len(execute_calls), 1)
        _, sql, params = execute_calls[0]
        self.assertIn("repo_slug = %s", sql)
        self.assertEqual(params[-1], 2)

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

    @unittest.skipUnless(
        os.getenv("RUN_PG_VECTOR_TESTS") == "1",
        "Set RUN_PG_VECTOR_TESTS=1 and PGVECTOR_TEST_DB_URL, or use bash scripts/run_pgvector_tests.sh",
    )
    def test_live_round_trip(self) -> None:
        db_url = os.getenv("PGVECTOR_TEST_DB_URL")
        if not db_url:
            self.skipTest("PGVECTOR_TEST_DB_URL is required")

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
                        file_path="src/app.py",
                        start_line=1,
                        end_line=1,
                    ),
                    VectorRecord(
                        vector=np.asarray([0.1, 0.9, 0.0], dtype=np.float32),
                        repo_slug="repo",
                        file_path="src/lib.py",
                        start_line=1,
                        end_line=1,
                    ),
                ]
            )
            results = store.search(
                query_vector=np.asarray([0.85, 0.15, 0.0], dtype=np.float32),
                k=1,
                repo_slug="repo",
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].file_path, "src/app.py")
        finally:
            with store._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {store._table_ref}")
                conn.commit()


if __name__ == "__main__":
    unittest.main()
