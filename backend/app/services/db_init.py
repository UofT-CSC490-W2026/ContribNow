from app.services.db import get_connection


def init_db() -> None:
    query = """
    CREATE TABLE IF NOT EXISTS onboarding_documents (
        id BIGSERIAL PRIMARY KEY,
        repo_id TEXT NOT NULL,
        repo_url TEXT NOT NULL,
        version INTEGER NOT NULL,
        storage_key TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (repo_id, version)
    );

    CREATE INDEX IF NOT EXISTS idx_onboarding_repo_id
    ON onboarding_documents (repo_id);
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()