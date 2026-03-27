import hashlib
from typing import Any

from app.services.db import get_connection


def normalize_repo_url(repo_url: str) -> str:
    return repo_url.strip().rstrip("/").lower()


def get_repo_id(repo_url: str) -> str:
    normalized = normalize_repo_url(repo_url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_cached_document(repo_url: str) -> dict[str, Any] | None:
    repo_id = get_repo_id(repo_url)

    query = """
    SELECT repo_id, repo_url, version, storage_key, created_at
    FROM onboarding_documents
    WHERE repo_id = %s
    ORDER BY version DESC
    LIMIT 1
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (repo_id,))
            row = cur.fetchone()

    if row is None:
        return None

    return {
        "repoId": row[0],
        "repoUrl": row[1],
        "version": row[2],
        "storageKey": row[3],
        "createdAt": row[4].isoformat() if row[4] else None,
    }


def get_next_version(repo_url: str) -> int:
    repo_id = get_repo_id(repo_url)

    query = """
    SELECT COALESCE(MAX(version), 0) + 1
    FROM onboarding_documents
    WHERE repo_id = %s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (repo_id,))
            row = cur.fetchone()
    
    if row is None:
        raise RuntimeError("Failed to get next version")

    return int(row[0])


def save_cached_document(
    repo_url: str,
    storage_key: str,
    version: int,
) -> dict[str, Any]:
    repo_id = get_repo_id(repo_url)
    normalized_repo_url = normalize_repo_url(repo_url)

    query = """
    INSERT INTO onboarding_documents (repo_id, repo_url, version, storage_key)
    VALUES (%s, %s, %s, %s)
    RETURNING repo_id, repo_url, version, storage_key, created_at
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (repo_id, normalized_repo_url, version, storage_key),
            )
            row = cur.fetchone()
        conn.commit()
    
    if row is None:
        raise RuntimeError("Failed to save cached document")

    return {
        "repoId": row[0],
        "repoUrl": row[1],
        "version": row[2],
        "storageKey": row[3],
        "createdAt": row[4].isoformat() if row[4] else None,
    }