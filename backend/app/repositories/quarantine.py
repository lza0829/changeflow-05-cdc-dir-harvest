from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def insert(
    conn: sqlite3.Connection,
    *,
    stream_id: int,
    run_id: int,
    seq: int,
    entity_key: str,
    reason: str,
    payload: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO quarantine(stream_id, run_id, seq, entity_key, reason, payload_json, created_at)
        VALUES (?,?,?,?,?,?,?)
        """,
        (
            stream_id,
            run_id,
            seq,
            entity_key,
            reason,
            json.dumps(payload, ensure_ascii=False),
            _now(),
        ),
    )


def list_quarantine(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, stream_id, run_id, seq, entity_key, reason, payload_json, created_at
        FROM quarantine ORDER BY id DESC
        """
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        out.append(item)
    return out


def count_quarantine(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) c FROM quarantine").fetchone()["c"])
