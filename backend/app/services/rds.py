import json
from typing import Any, cast

from psycopg import sql, Error

from app.services.db import get_connection
from app.config import logger
from app.models import ChatMessage


def create_kv_table_in_rds(table_name: str) -> dict[str, str]:
    query = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {table} (
            key TEXT PRIMARY KEY,
            value JSONB NOT NULL
        )
    """).format(
        table=sql.Identifier(table_name),
    )

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
            conn.commit()

        return {
            "status": "success",
            "message": f"RDS table '{table_name}' created successfully",
        }

    except Error as e:
        return {
            "status": "error",
            "message": f"Failed to create RDS table: {str(e)}",
        }


def save_value_to_rds(
    table_name: str,
    key: str,
    value: Any,
) -> dict[str, str]:
    query = sql.SQL("""
        INSERT INTO {table} (key, value)
        VALUES (%s, %s::jsonb)
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value
    """).format(
        table=sql.Identifier(table_name),
    )

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (key, json.dumps(value)))
            conn.commit()

        return {
            "status": "success",
            "message": f"Value saved to RDS table '{table_name}' successfully",
        }

    except Error as e:
        return {
            "status": "error",
            "message": f"Failed to save value to RDS: {str(e)}",
        }


def load_value_from_rds(
    table_name: str,
    key: str,
) -> dict[str, Any]:
    query = sql.SQL("""
        SELECT *
        FROM {table}
        WHERE key = %s
        LIMIT 1
    """).format(
        table=sql.Identifier(table_name),
    )

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (key,))
                row = cur.fetchone()

                if row is None:
                    return {
                        "status": "error",
                        "message": f"No value found for key '{key}' in table '{table_name}'",
                    }

                if cur.description is None:
                    return {
                        "status": "error",
                        "message": "Failed to retrieve column information from RDS",
                    }

                column_names = [desc.name for desc in cur.description]

        return {
            "status": "success",
            "row": dict(zip(column_names, row)),
        }

    except Error as e:
        return {
            "status": "error",
            "message": f"Failed to load value from RDS: {str(e)}",
        }


def save_onboarding_doc_repo(
    access_key: str,
    repo_slug: str,
) -> bool:
    query = """
    INSERT INTO onboarding_user_repos (access_key, repo_slug)
    VALUES (%s, %s)
    ON CONFLICT (access_key, repo_slug) DO NOTHING
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (access_key, repo_slug))
            conn.commit()
        return True
    
    except Error as e:
        logger.error(f"Failed to save onboarding doc metadata to RDS with access_key = {access_key}, repo_slug = {repo_slug}: {str(e)}")
        return False


def load_onboarding_doc_repos(access_key: str) -> list[str]:
    query = """
    SELECT repo_slug
    FROM onboarding_user_repos
    WHERE access_key = %s
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (access_key,))
                rows = cur.fetchall()
                repo_slugs = [row[0] for row in rows]
        return repo_slugs

    except Error as e:
        logger.error(f"Failed to load onboarding doc metadata from RDS with access_key = {access_key}: {str(e)}")
        return []


def delete_onboarding_doc_repo(access_key: str, repo_slug: str) -> int:
    query = """
    DELETE FROM onboarding_user_repos
    WHERE access_key = %s AND repo_slug = %s
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (access_key, repo_slug))
                deleted_cnt = cur.rowcount
            conn.commit()
        return deleted_cnt

    except Error as e:
        logger.error(f"Failed to delete onboarding doc metadata from RDS with access_key = {access_key}, repo_slug = {repo_slug}: {str(e)}")
        return -1


def save_chat_to_rds(
    access_key: str,
    chat: ChatMessage,
) -> bool:
    query = """
    INSERT INTO chat_history (access_key, role, message)
    VALUES (%s, %s, %s)
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (access_key, chat.role, chat.message),
                )
            conn.commit()
        return True

    except Error as e:
        logger.error(f"Failed to save chat history to RDS with access_key = {access_key}: {str(e)}")
        return False


def load_chat_history_from_rds(access_key: str) -> list[ChatMessage]:
    query = """
    SELECT role, message, created_at
    FROM chat_history
    WHERE access_key = %s
    ORDER BY created_at ASC, id ASC
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (access_key,))
                rows = cur.fetchall()

        return cast(list[ChatMessage], [
                {
                    "role": row[0],
                    "message": row[1],
                    "created_at": row[2].isoformat(),
                }
                for row in rows
            ]
        )

    except Error as e:
        logger.error(f"Failed to load chat history from RDS with access_key = {access_key}: {str(e)}")
        return []


def delete_chat_history_from_rds(access_key: str) -> int:
    query = """
    DELETE FROM chat_history
    WHERE access_key = %s
    """

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (access_key,))
                deleted_cnt = cur.rowcount
            conn.commit()
        return deleted_cnt

    except Error as e:
        logger.error(f"Failed to delete chat history from RDS with access_key = {access_key}: {str(e)}")
        return -1