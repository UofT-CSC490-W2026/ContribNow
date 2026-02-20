import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.pipeline.utils import read_json, sha256_hex, utc_now

SCHEMA_VERSION = 1
FORBIDDEN_KEY_PATTERNS = (
    re.compile(r"commit_message", re.IGNORECASE),
    re.compile(r"author_email", re.IGNORECASE),
    re.compile(r"absolute_path", re.IGNORECASE),
)


def _hash_with_tenant_salt(raw: str, tenant_salt: str) -> str:
    return sha256_hex(f"{tenant_salt}::{raw}")


def _normalize_repo_ref(repo_ref: str) -> str:
    return repo_ref.strip().lower().rstrip("/")


def _normalize_rel_path(path: str) -> str:
    return path.replace("\\", "/").strip().lstrip("/")


def _ensure_cloud_safe(payload: dict[str, Any]) -> None:
    for key, value in payload.items():
        for pattern in FORBIDDEN_KEY_PATTERNS:
            if pattern.search(key):
                raise ValueError(f"Forbidden field in cloud payload: {key}")
        if isinstance(value, dict):
            _ensure_cloud_safe(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _ensure_cloud_safe(item)


def _extract_file_fingerprints(
    transform_payload: dict[str, Any], tenant_salt: str
) -> list[dict[str, Any]]:
    transform_meta = transform_payload.get("transform_metadata", {})
    ingest_path_raw = transform_meta.get("source_ingest_path")
    if not isinstance(ingest_path_raw, str) or not ingest_path_raw:
        return []

    ingest_path = Path(ingest_path_raw)
    if not ingest_path.exists():
        return []

    ingest_payload = read_json(ingest_path)
    files = ingest_payload.get("files", [])
    if not isinstance(files, list):
        return []

    fingerprints: list[dict[str, Any]] = []
    for file_path in files:
        if not isinstance(file_path, str):
            continue
        canonical = _normalize_rel_path(file_path)
        fingerprints.append(
            {
                "file_path_hash": _hash_with_tenant_salt(canonical, tenant_salt),
                "content_hash": None,
            }
        )
    return fingerprints


def _sanitize_structure_metrics(
    structure_summary: dict[str, Any], tenant_salt: str
) -> dict[str, Any]:
    top_levels = structure_summary.get("top_level_directories", [])
    file_types = structure_summary.get("file_type_counts", [])

    hashed_top_levels: list[dict[str, Any]] = []
    if isinstance(top_levels, list):
        for entry in top_levels:
            if not isinstance(entry, dict):
                continue
            raw_path = str(entry.get("path") or "")
            hashed_top_levels.append(
                {
                    "dir_hash": _hash_with_tenant_salt(
                        _normalize_rel_path(raw_path), tenant_salt
                    ),
                    "file_count": int(entry.get("file_count") or 0),
                }
            )

    ext_counts: list[dict[str, Any]] = []
    if isinstance(file_types, list):
        for entry in file_types:
            if not isinstance(entry, dict):
                continue
            ext_counts.append(
                {
                    "extension": str(entry.get("extension") or ""),
                    "count": int(entry.get("count") or 0),
                }
            )

    return {
        "total_files": int(structure_summary.get("total_files") or 0),
        "top_level_directories": hashed_top_levels,
        "file_type_counts": ext_counts,
    }


def build_cloud_safe_payload(
    transform_json_path: Path,
    tenant_id: str,
    user_id: str,
    tenant_salt: str,
    local_run_id: str | None = None,
) -> dict[str, Any]:
    """Project transform output into a cloud-safe, hashed metadata payload."""
    payload = read_json(Path(transform_json_path))
    repo_url = str(payload.get("repo_url") or "")
    repo_slug = str(payload.get("repo_slug") or "")
    head_commit = str(payload.get("head_commit") or "")
    canonical_repo_ref = _normalize_repo_ref(repo_url or repo_slug)

    repo_fingerprint = _hash_with_tenant_salt(canonical_repo_ref, tenant_salt)
    canonical_repo_ref_hash = _hash_with_tenant_salt(canonical_repo_ref, tenant_salt)
    version_key = sha256_hex(f"{tenant_id}:{repo_fingerprint}:{head_commit}")

    structure_summary = payload.get("structure_summary", {})
    hotspots_raw = payload.get("hotspots", [])

    hotspot_metrics: list[dict[str, Any]] = []
    for item in hotspots_raw:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "")
        hotspot_metrics.append(
            {
                "file_hash": _hash_with_tenant_salt(
                    _normalize_rel_path(raw_path), tenant_salt
                ),
                "touch_count": int(item.get("touch_count") or 0),
                "last_touched": item.get("last_touched"),
            }
        )

    cloud_payload: dict[str, Any] = {
        "tenant_id": tenant_id,
        "repo_fingerprint": repo_fingerprint,
        "canonical_repo_ref_hash": canonical_repo_ref_hash,
        "head_commit": head_commit,
        "version_key": version_key,
        "structure_metrics": _sanitize_structure_metrics(
            structure_summary, tenant_salt
        ),
        "hotspot_metrics": hotspot_metrics,
        "file_fingerprints": _extract_file_fingerprints(payload, tenant_salt),
        "sync_metadata": {
            "user_id": user_id,
            "local_run_id": local_run_id or str(uuid.uuid4()),
            "synced_at": utc_now(),
            "schema_version": SCHEMA_VERSION,
        },
    }

    _ensure_cloud_safe(cloud_payload)
    return cloud_payload


@dataclass
class SyncResult:
    status: str
    version_key: str
    synced_at: str
    message: str | None = None


class MemorySyncStore:
    """Lightweight deterministic store for tests of merge/idempotency semantics."""

    def __init__(self) -> None:
        self.tenants: set[str] = set()
        self.repos: dict[tuple[str, str], dict[str, Any]] = {}
        self.versions: dict[str, dict[str, Any]] = {}
        self.version_hotspots: dict[tuple[str, str], dict[str, Any]] = {}
        self.version_files: dict[tuple[str, str], dict[str, Any]] = {}
        self.sync_runs: list[dict[str, Any]] = []

    def sync_cloud_safe(self, payload: dict[str, Any]) -> SyncResult:
        tenant_id = str(payload["tenant_id"])
        repo_fingerprint = str(payload["repo_fingerprint"])
        version_key = str(payload["version_key"])
        synced_at = str(payload["sync_metadata"]["synced_at"])

        self.tenants.add(tenant_id)
        self.repos[(tenant_id, repo_fingerprint)] = {
            "tenant_id": tenant_id,
            "repo_fingerprint": repo_fingerprint,
            "canonical_repo_ref_hash": payload["canonical_repo_ref_hash"],
        }

        if version_key in self.versions:
            version = self.versions[version_key]
            version["last_seen_at"] = synced_at
            version["structure_json"] = payload["structure_metrics"]
        else:
            self.versions[version_key] = {
                "tenant_id": tenant_id,
                "repo_fingerprint": repo_fingerprint,
                "head_commit": payload["head_commit"],
                "structure_json": payload["structure_metrics"],
                "schema_version": payload["sync_metadata"]["schema_version"],
                "first_seen_at": synced_at,
                "last_seen_at": synced_at,
            }

        for hotspot in payload.get("hotspot_metrics", []):
            file_hash = str(hotspot["file_hash"])
            self.version_hotspots[(version_key, file_hash)] = {
                "touch_count": int(hotspot["touch_count"]),
                "last_touched": hotspot.get("last_touched"),
            }

        for file_fp in payload.get("file_fingerprints", []):
            file_hash = str(file_fp["file_path_hash"])
            self.version_files[(version_key, file_hash)] = {
                "content_hash": file_fp.get("content_hash"),
            }

        self.sync_runs.append(
            {
                "tenant_id": tenant_id,
                "user_id": payload["sync_metadata"]["user_id"],
                "repo_fingerprint": repo_fingerprint,
                "head_commit": payload["head_commit"],
                "version_key": version_key,
                "status": "success",
                "created_at": synced_at,
            }
        )
        return SyncResult(
            status="success", version_key=version_key, synced_at=synced_at
        )


class PostgresSyncStore:
    def __init__(self, db_url: str) -> None:
        self.db_url = db_url

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for Postgres cloud sync. Install with: uv add psycopg[binary]"
            ) from exc
        return psycopg.connect(self.db_url)

    def apply_schema(self, sql_path: Path) -> None:
        sql = Path(sql_path).read_text(encoding="utf-8")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()

    def sync_cloud_safe(self, payload: dict[str, Any]) -> SyncResult:
        tenant_id = str(payload["tenant_id"])
        repo_fingerprint = str(payload["repo_fingerprint"])
        canonical_repo_ref_hash = str(payload["canonical_repo_ref_hash"])
        head_commit = str(payload["head_commit"])
        version_key = str(payload["version_key"])
        sync_metadata = payload["sync_metadata"]
        user_id = str(sync_metadata["user_id"])
        synced_at = str(sync_metadata["synced_at"])
        schema_version = int(sync_metadata["schema_version"])
        structure_json = json.dumps(payload["structure_metrics"])

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tenants (tenant_id, name, created_at)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (tenant_id) DO NOTHING
                    """,
                    (tenant_id, tenant_id, synced_at),
                )
                cur.execute(
                    """
                    INSERT INTO repos (tenant_id, repo_fingerprint, canonical_repo_ref_hash)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (tenant_id, repo_fingerprint)
                    DO UPDATE SET canonical_repo_ref_hash = EXCLUDED.canonical_repo_ref_hash
                    RETURNING repo_id
                    """,
                    (tenant_id, repo_fingerprint, canonical_repo_ref_hash),
                )
                repo_id = cur.fetchone()[0]

                cur.execute(
                    """
                    INSERT INTO repo_versions (
                        repo_id, head_commit, version_key, structure_json, schema_version, first_seen_at, last_seen_at
                    )
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
                    ON CONFLICT (version_key)
                    DO UPDATE SET
                        structure_json = EXCLUDED.structure_json,
                        schema_version = EXCLUDED.schema_version,
                        last_seen_at = EXCLUDED.last_seen_at
                    RETURNING version_id
                    """,
                    (
                        repo_id,
                        head_commit,
                        version_key,
                        structure_json,
                        schema_version,
                        synced_at,
                        synced_at,
                    ),
                )
                version_id = cur.fetchone()[0]

                for hotspot in payload.get("hotspot_metrics", []):
                    cur.execute(
                        """
                        INSERT INTO version_hotspots (version_id, file_hash, touch_count, last_touched)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (version_id, file_hash)
                        DO UPDATE SET
                            touch_count = EXCLUDED.touch_count,
                            last_touched = EXCLUDED.last_touched
                        """,
                        (
                            version_id,
                            hotspot["file_hash"],
                            int(hotspot["touch_count"]),
                            hotspot.get("last_touched"),
                        ),
                    )

                for file_fp in payload.get("file_fingerprints", []):
                    cur.execute(
                        """
                        INSERT INTO version_files (version_id, file_path_hash, content_hash)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (version_id, file_path_hash)
                        DO UPDATE SET content_hash = EXCLUDED.content_hash
                        """,
                        (
                            version_id,
                            file_fp["file_path_hash"],
                            file_fp.get("content_hash"),
                        ),
                    )

                cur.execute(
                    """
                    INSERT INTO sync_runs (
                        sync_run_id, tenant_id, user_id, repo_fingerprint, head_commit, version_key, status, error_summary, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        tenant_id,
                        user_id,
                        repo_fingerprint,
                        head_commit,
                        version_key,
                        "success",
                        synced_at,
                    ),
                )
            conn.commit()

        return SyncResult(
            status="success", version_key=version_key, synced_at=synced_at
        )


def sync_cloud_safe(
    transform_json_path: Path,
    tenant_id: str,
    user_id: str,
    tenant_salt: str,
    db_url: str,
    local_run_id: str | None = None,
    schema_sql_path: Path | None = None,
    apply_schema: bool = False,
) -> SyncResult:
    """Build and sync cloud-safe metadata for one transformed repo artifact."""
    payload = build_cloud_safe_payload(
        transform_json_path=transform_json_path,
        tenant_id=tenant_id,
        user_id=user_id,
        tenant_salt=tenant_salt,
        local_run_id=local_run_id,
    )
    store = PostgresSyncStore(db_url)
    if apply_schema and schema_sql_path is not None:
        store.apply_schema(schema_sql_path)
    return store.sync_cloud_safe(payload)


def is_cloud_sync_enabled(flag: str | None = None) -> bool:
    raw = flag if flag is not None else os.getenv("ENABLE_CLOUD_SYNC", "false")
    return raw.strip().lower() in {"1", "true", "yes", "on"}
