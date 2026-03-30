from app.services.db import get_connection
from app.services.pgvector import PgVectorStore


def init_db_onboarding_doc() -> None:
    query = """
    CREATE TABLE IF NOT EXISTS onboarding_user_repos (
        id BIGSERIAL PRIMARY KEY,
        access_key TEXT NOT NULL,
        repo_slug TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (access_key, repo_slug)
    );

    CREATE INDEX IF NOT EXISTS idx_onboarding_user_repos_access_key
    ON onboarding_user_repos (access_key);
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()


def init_db_chat_history() -> None:
    query = """
    CREATE TABLE IF NOT EXISTS chat_history (
        id BIGSERIAL PRIMARY KEY,
        access_key TEXT NOT NULL,
        repo_slug TEXT NOT NULL,
        role TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_chat_history_access_key_repo_slug_created_at
    ON chat_history (access_key, repo_slug, created_at);
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
        conn.commit()


def init_pgvectorstore() -> PgVectorStore:    
    pgvectorstore = PgVectorStore(
        schema_name="public",
        table_name="rag_vectors",
        embedding_dimensions=32,
    )
    pgvectorstore.ensure_schema()

    return pgvectorstore
