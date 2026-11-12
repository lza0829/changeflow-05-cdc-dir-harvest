from __future__ import annotations

import json
import sqlite3
from typing import Any


def insert_ledger(
    conn: sqlite3.Connection,
    *,
    stream_id: int,
    run_id: int | None,
    event: dict[str, Any],
    disposition: str,
    harvest_task_id: int | None = None,
    harvest_shard_id: int | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO change_ledger(
            stream_id, run_id, seq, op, entity_key, event_ts, payload_json, disposition,
            harvest_task_id, harvest_shard_id
        )
        VALUES (?,?,?,?,?,?,?,?,?,?)
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
            harvest_task_id,
            harvest_shard_id,
        ),
    )
    return int(cur.lastrowid)


def set_disposition(
    conn: sqlite3.Connection,
    ledger_id: int,
    *,
    disposition: str,
    run_id: int,
) -> None:
    conn.execute(
        "UPDATE change_ledger SET disposition=?, run_id=? WHERE id=?",
        (disposition, run_id, ledger_id),
    )


def pending_for_task(conn: sqlite3.Connection, task_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, stream_id, run_id, seq, op, entity_key, event_ts, payload_json, disposition,
               harvest_task_id, harvest_shard_id
        FROM change_ledger
        WHERE harvest_task_id=? AND disposition='collected'
        ORDER BY seq, id
        """,
        (task_id,),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        out.append(item)
    return out


def disposition_counts_for_task(conn: sqlite3.Connection, task_id: int) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT disposition, COUNT(*) c FROM change_ledger
        WHERE harvest_task_id=? GROUP BY disposition
        """,
        (task_id,),
    ).fetchall()
    return {r["disposition"]: int(r["c"]) for r in rows}


def count_for_run(conn: sqlite3.Connection, run_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) c FROM change_ledger WHERE run_id=?", (run_id,)
        ).fetchone()["c"]
    )


def list_ledger(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, stream_id, run_id, seq, op, entity_key, event_ts, payload_json, disposition,
               harvest_task_id, harvest_shard_id
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
