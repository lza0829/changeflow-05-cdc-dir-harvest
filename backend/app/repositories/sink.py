from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upsert(
    conn: sqlite3.Connection,
    *,
    stream_id: int,
    entity_key: str,
    payload: dict[str, Any],
    seq: int,
    event_ts: str,
) -> None:
    conn.execute(
        """
        INSERT INTO sink_records(stream_id, entity_key, payload_json, last_seq, last_event_ts, updated_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(stream_id, entity_key) DO UPDATE SET
            payload_json=excluded.payload_json,
            last_seq=excluded.last_seq,
            last_event_ts=excluded.last_event_ts,
            updated_at=excluded.updated_at
        """,
        (
            stream_id,
            entity_key,
            json.dumps(payload, ensure_ascii=False),
            seq,
            event_ts,
            _now(),
        ),
    )


def delete(conn: sqlite3.Connection, *, stream_id: int, entity_key: str) -> None:
    conn.execute(
        "DELETE FROM sink_records WHERE stream_id=? AND entity_key=?",
        (stream_id, entity_key),
    )


def list_sink(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, stream_id, entity_key, payload_json, last_seq, last_event_ts, updated_at
        FROM sink_records ORDER BY stream_id, entity_key
        """
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        out.append(item)
    return out


def count_sink(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) c FROM sink_records").fetchone()["c"])
