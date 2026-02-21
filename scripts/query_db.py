#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value


def _get_db_url(cli_url: str | None, env_file: Path) -> str:
    _load_env_file(env_file)
    db_url = cli_url or os.getenv("CLOUD_DB_URL")
    if not db_url:
        raise RuntimeError("Missing DB URL. Pass --db-url or set CLOUD_DB_URL in .env/environment.")
    return db_url


def _run_query(db_url: str, query_name: str, limit: int, tenant_id: str | None) -> list[dict[str, Any]]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required. Install with: pip install -r requirements-cloud.txt") from exc

    queries: dict[str, tuple[str, tuple[Any, ...]]] = {
        "summary": (
            """
            SELECT
              (SELECT COUNT(*) FROM tenants) AS tenants,
              (SELECT COUNT(*) FROM repos) AS repos,
              (SELECT COUNT(*) FROM repo_versions) AS repo_versions,
              (SELECT COUNT(*) FROM version_hotspots) AS version_hotspots,
              (SELECT COUNT(*) FROM version_files) AS version_files,
              (SELECT COUNT(*) FROM sync_runs) AS sync_runs
            """,
            (),
        ),
        "sync-runs": (
            """
            SELECT tenant_id, user_id, repo_fingerprint, head_commit, version_key, status, created_at
            FROM sync_runs
            WHERE (%s::text IS NULL OR tenant_id = %s)
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, tenant_id, limit),
        ),
        "versions": (
            """
            SELECT r.tenant_id, rv.version_key, rv.head_commit, rv.first_seen_at, rv.last_seen_at
            FROM repo_versions rv
            JOIN repos r ON r.repo_id = rv.repo_id
            WHERE (%s::text IS NULL OR r.tenant_id = %s)
            ORDER BY rv.last_seen_at DESC
            LIMIT %s
            """,
            (tenant_id, tenant_id, limit),
        ),
        "hotspots": (
            """
            SELECT r.tenant_id, rv.version_key, vh.file_hash, vh.touch_count, vh.last_touched
            FROM version_hotspots vh
            JOIN repo_versions rv ON rv.version_id = vh.version_id
            JOIN repos r ON r.repo_id = rv.repo_id
            WHERE (%s::text IS NULL OR r.tenant_id = %s)
            ORDER BY vh.touch_count DESC, vh.last_touched DESC NULLS LAST
            LIMIT %s
            """,
            (tenant_id, tenant_id, limit),
        ),
    }

    if query_name not in queries:
        raise RuntimeError(f"Unknown query '{query_name}'. Choose from: {', '.join(sorted(queries.keys()))}")

    sql, params = queries[query_name]
    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Simple read-only query helper for ContribNow cloud DB.")
    parser.add_argument(
        "--query",
        default="summary",
        choices=["summary", "sync-runs", "versions", "hotspots"],
        help="Preset query to execute.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Row limit for list-style queries.")
    parser.add_argument("--tenant-id", default=None, help="Optional tenant filter for list-style queries.")
    parser.add_argument("--db-url", default=None, help="Optional DB URL override.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="Path to dotenv file.")
    args = parser.parse_args()

    db_url = _get_db_url(args.db_url, args.env_file)
    rows = _run_query(db_url, args.query, args.limit, args.tenant_id)
    print(json.dumps(rows, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
