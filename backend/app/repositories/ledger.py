from __future__ import annotations

import json
import sqlite3
from typing import Any


def insert_ledger(
    conn: sqlite3.Connection,
    *,
    stream_id: int,
    run_id: int,
    event: dict[str, Any],
    disposition: str,
) -> None:
    conn.execute(
        """
        INSERT INTO change_ledger(stream_id, run_id, seq, op, entity_key, event_ts, payload_json, disposition)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            stream_id,
            run_id,
            int(event["seq"]),
            event["op"],
            event["entity_key"],
            event["event_ts"],
            json.dumps(event.get("payload") or {}, ensure_ascii=False),
            disposition,
        ),
    )


def list_ledger(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, stream_id, run_id, seq, op, entity_key, event_ts, payload_json, disposition
        FROM change_ledger ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        out.append(item)
    return out
