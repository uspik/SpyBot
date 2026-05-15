from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from config import DATABASE_PATH, RETENTION_DAYS


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS connections (
                business_connection_id TEXT PRIMARY KEY,
                user_chat_id INTEGER NOT NULL,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                connected_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS messages (
                business_connection_id TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                from_user_id INTEGER,
                from_username TEXT,
                from_first_name TEXT,
                chat_title TEXT,
                chat_type TEXT,
                content TEXT NOT NULL,
                message_date INTEGER,
                media_path TEXT,
                PRIMARY KEY (business_connection_id, chat_id, message_id)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_connection
                ON messages (business_connection_id);

            CREATE INDEX IF NOT EXISTS idx_messages_date
                ON messages (message_date);
            """
        )
        _ensure_column(conn, "messages", "media_path", "media_path TEXT")


def upsert_connection(
    business_connection_id: str,
    user_chat_id: int,
    user_id: int | None,
    username: str | None,
    first_name: str | None,
    is_enabled: bool,
    connected_at: int,
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO connections (
                business_connection_id, user_chat_id, user_id, username,
                first_name, is_enabled, connected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(business_connection_id) DO UPDATE SET
                user_chat_id = excluded.user_chat_id,
                user_id = excluded.user_id,
                username = excluded.username,
                first_name = excluded.first_name,
                is_enabled = excluded.is_enabled,
                connected_at = excluded.connected_at
            """,
            (
                business_connection_id,
                user_chat_id,
                user_id,
                username,
                first_name,
                int(is_enabled),
                connected_at,
            ),
        )


def get_owner_chat_id(business_connection_id: str) -> int | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT user_chat_id FROM connections
            WHERE business_connection_id = ? AND is_enabled = 1
            """,
            (business_connection_id,),
        ).fetchone()
    return int(row["user_chat_id"]) if row else None


def get_owner_user_id(business_connection_id: str) -> int | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT user_id FROM connections
            WHERE business_connection_id = ? AND is_enabled = 1
            """,
            (business_connection_id,),
        ).fetchone()
    if row and row["user_id"] is not None:
        return int(row["user_id"])
    return None


def get_connection_by_owner(user_chat_id: int) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute(
            """
            SELECT * FROM connections
            WHERE user_chat_id = ? AND is_enabled = 1
            ORDER BY connected_at DESC
            """,
            (user_chat_id,),
        ).fetchall()


def is_foreign_message(
    business_connection_id: str, from_user_id: int | None
) -> bool:
    if from_user_id is None:
        return False
    owner_id = get_owner_user_id(business_connection_id)
    if owner_id is None:
        return False
    return from_user_id != owner_id


def save_message(
    business_connection_id: str,
    chat_id: int,
    message_id: int,
    from_user_id: int | None,
    from_username: str | None,
    from_first_name: str | None,
    chat_title: str | None,
    chat_type: str | None,
    content: str,
    message_date: int | None,
    media_path: str | None = None,
    *,
    keep_media_path: bool = False,
) -> str | None:
    """Сохраняет сообщение. Возвращает старый media_path, если файл нужно удалить."""
    old_media_path: str | None = None
    with get_db() as conn:
        old = conn.execute(
            """
            SELECT media_path FROM messages
            WHERE business_connection_id = ? AND chat_id = ? AND message_id = ?
            """,
            (business_connection_id, chat_id, message_id),
        ).fetchone()
        if old and old["media_path"]:
            old_media_path = old["media_path"]

        resolved_media = media_path
        if keep_media_path and media_path is None and old and old["media_path"]:
            resolved_media = old["media_path"]

        conn.execute(
            """
            INSERT INTO messages (
                business_connection_id, chat_id, message_id,
                from_user_id, from_username, from_first_name,
                chat_title, chat_type, content, message_date, media_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(business_connection_id, chat_id, message_id) DO UPDATE SET
                from_user_id = excluded.from_user_id,
                from_username = excluded.from_username,
                from_first_name = excluded.from_first_name,
                chat_title = excluded.chat_title,
                chat_type = excluded.chat_type,
                content = excluded.content,
                message_date = excluded.message_date,
                media_path = COALESCE(excluded.media_path, messages.media_path)
            """,
            (
                business_connection_id,
                chat_id,
                message_id,
                from_user_id,
                from_username,
                from_first_name,
                chat_title,
                chat_type,
                content,
                message_date,
                resolved_media,
            ),
        )

    if media_path and old_media_path and old_media_path != media_path:
        return old_media_path
    return None


def get_message(
    business_connection_id: str, chat_id: int, message_id: int
) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            """
            SELECT * FROM messages
            WHERE business_connection_id = ? AND chat_id = ? AND message_id = ?
            """,
            (business_connection_id, chat_id, message_id),
        ).fetchone()


def get_messages(
    business_connection_id: str, chat_id: int, message_ids: list[int]
) -> list[sqlite3.Row]:
    if not message_ids:
        return []
    placeholders = ",".join("?" * len(message_ids))
    with get_db() as conn:
        return conn.execute(
            f"""
            SELECT * FROM messages
            WHERE business_connection_id = ?
              AND chat_id = ?
              AND message_id IN ({placeholders})
            """,
            [business_connection_id, chat_id, *message_ids],
        ).fetchall()


def delete_messages(
    business_connection_id: str, chat_id: int, message_ids: list[int]
) -> list[str]:
    if not message_ids:
        return []
    placeholders = ",".join("?" * len(message_ids))
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT media_path FROM messages
            WHERE business_connection_id = ?
              AND chat_id = ?
              AND message_id IN ({placeholders})
              AND media_path IS NOT NULL
            """,
            [business_connection_id, chat_id, *message_ids],
        ).fetchall()
        conn.execute(
            f"""
            DELETE FROM messages
            WHERE business_connection_id = ?
              AND chat_id = ?
              AND message_id IN ({placeholders})
            """,
            [business_connection_id, chat_id, *message_ids],
        )
    return [row["media_path"] for row in rows if row["media_path"]]


def purge_old_messages(retention_days: int | None = None) -> list[str]:
    days = retention_days if retention_days is not None else RETENTION_DAYS
    cutoff = int(time.time()) - days * 24 * 60 * 60
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT media_path FROM messages
            WHERE message_date IS NOT NULL AND message_date < ?
              AND media_path IS NOT NULL
            """,
            (cutoff,),
        ).fetchall()
        conn.execute(
            """
            DELETE FROM messages
            WHERE message_date IS NOT NULL AND message_date < ?
            """,
            (cutoff,),
        )
    return [row["media_path"] for row in rows if row["media_path"]]


def dump_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)
