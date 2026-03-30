from __future__ import annotations

import math
import re
from typing import Any

import numpy as np

from app.services.pgvector_interfaces import FloatVector, SearchResult, VectorRecord

from app.services.db import get_connection

_SQL_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PgVectorStore:
    """
    PostgreSQL/pgvector-backed store with a minimal deterministic record shape.
    """

    def __init__(
        self,
        *,
        schema_name: str = "public",
        table_name: str = "rag_vectors",
        embedding_dimensions: int,
    ) -> None:
        if embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be > 0")
        self.schema_name = self._validate_identifier("schema_name", schema_name)
        self.table_name = self._validate_identifier("table_name", table_name)
        self.embedding_dimensions = embedding_dimensions

    @property
    def name(self) -> str:
        return "pgvector"

    def ensure_schema(self) -> None:
        vector_type = f"vector({self.embedding_dimensions})"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    f"""
                    CREATE SCHEMA IF NOT EXISTS {self.schema_name};

                    CREATE TABLE IF NOT EXISTS {self._table_ref} (
                        repo_slug TEXT NOT NULL,
                        head_commit TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        start_line INTEGER NOT NULL,
                        end_line INTEGER NOT NULL,
                        embedding {vector_type} NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (repo_slug, head_commit, file_path, start_line, end_line)
                    );
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_repo_slug_idx
                    ON {self._table_ref} (repo_slug);
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_file_path_idx
                    ON {self._table_ref} (file_path);
                    """
                )
            conn.commit()

    def upsert(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0

        rows = []
        for record in records:
            self._validate_dimensions(record.vector)
            rows.append(
                (
                    record.repo_slug,
                    record.head_commit,
                    record.file_path,
                    int(record.start_line),
                    int(record.end_line),
                    self._vector_literal(record.vector),
                )
            )

        sql = f"""
            INSERT INTO {self._table_ref} (
                repo_slug,
                head_commit,
                file_path,
                start_line,
                end_line,
                embedding
            )
            VALUES (%s, %s, %s, %s, %s, %s::vector)
            ON CONFLICT (repo_slug, head_commit, file_path, start_line, end_line)
            DO UPDATE SET
                embedding = EXCLUDED.embedding,
                updated_at = NOW()
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
            conn.commit()
        return len(records)

    def delete_by_repo(self, repo_slug: str) -> int:
        if not repo_slug:
            return 0
        sql = f"DELETE FROM {self._table_ref} WHERE repo_slug = %s"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (repo_slug,))
                deleted = int(cur.rowcount or 0)
            conn.commit()
        return deleted

    def search(
        self,
        query_vector: FloatVector,
        k: int = 5,
        *,
        repo_slug: str | None = None,
        head_commit: str | None = None,
        file_path: str | None = None,
    ) -> list[SearchResult]:
        if k <= 0:
            return []

        self._validate_dimensions(query_vector)
        where_clauses: list[str] = []
        params: list[Any] = []
        if repo_slug is not None:
            where_clauses.append("repo_slug = %s")
            params.append(repo_slug)
        if head_commit is not None:
            where_clauses.append("head_commit = %s")
            params.append(head_commit)
        if file_path is not None:
            where_clauses.append("file_path = %s")
            params.append(file_path)

        sql = f"""
            SELECT
                repo_slug,
                head_commit,
                file_path,
                start_line,
                end_line,
                (embedding <=> %s::vector) AS distance
            FROM {self._table_ref}
        """
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += " ORDER BY distance ASC LIMIT %s"

        params = [self._vector_literal(query_vector), *params, k]

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        results: list[SearchResult] = []
        for row in rows:
            distance = float(row[5])
            results.append(
                SearchResult(
                    score=1.0 - distance,
                    repo_slug=str(row[0]),
                    head_commit=str(row[1]),
                    file_path=str(row[2]),
                    start_line=int(row[3]),
                    end_line=int(row[4]),
                    vector=None,
                )
            )
        return results

    @property
    def _table_ref(self) -> str:
        return f"{self.schema_name}.{self.table_name}"

    def _connect(self) -> Any:
        return get_connection()

    @staticmethod
    def _validate_identifier(label: str, value: str) -> str:
        if not value or not value.strip():
            raise ValueError(f"{label} must be a non-empty string")
        if not _SQL_IDENT_RE.match(value):
            raise ValueError(
                f"{label} must match SQL identifier pattern [A-Za-z_][A-Za-z0-9_]*"
            )
        return value

    def _validate_dimensions(self, vector: FloatVector) -> None:
        arr = np.asarray(vector, dtype=np.float32)
        if arr.ndim != 1 or arr.size == 0:
            raise ValueError("vector must be a non-empty 1D array")
        if arr.shape[0] != self.embedding_dimensions:
            raise ValueError(
                f"vector has dimension {arr.shape[0]}, expected {self.embedding_dimensions}"
            )

    @staticmethod
    def _vector_literal(vector: FloatVector) -> str:
        arr = np.asarray(vector, dtype=np.float32)
        if arr.ndim != 1 or arr.size == 0:
            raise ValueError("vector must be a non-empty 1D array")

        formatted: list[str] = []
        for value in arr:
            scalar = float(value)
            if not math.isfinite(scalar):
                raise ValueError("vector values must be finite floats")
            formatted.append(format(scalar, ".12g"))
        return "[" + ",".join(formatted) + "]"
