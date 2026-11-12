from __future__ import annotations

import sqlite3
from typing import Any


def list_streams(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, fixture_path, entity_type, apply_cursor, enabled, note FROM streams ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


def get_stream(conn: sqlite3.Connection, stream_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, name, fixture_path, entity_type, apply_cursor, enabled, note FROM streams WHERE id=?",
        (stream_id,),
    ).fetchone()
    return dict(row) if row else None


def set_cursor(conn: sqlite3.Connection, stream_id: int, cursor: int) -> None:
    conn.execute("UPDATE streams SET apply_cursor=? WHERE id=?", (cursor, stream_id))


def set_enabled(conn: sqlite3.Connection, stream_id: int, enabled: bool) -> None:
    conn.execute("UPDATE streams SET enabled=? WHERE id=?", (1 if enabled else 0, stream_id))
