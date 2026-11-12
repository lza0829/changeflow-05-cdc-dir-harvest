from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_run(
    conn: sqlite3.Connection,
    stream_id: int,
    cursor_before: int,
    harvest_task_id: int | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO apply_runs(
            stream_id, status, loaded_count, applied_count, quarantined_count, skipped_count,
            cursor_before, cursor_after, report_json, created_at, harvest_task_id
        ) VALUES (?,?,0,0,0,0,?,?,?,?,?)
        """,
        (stream_id, "running", cursor_before, cursor_before, "{}", _now(), harvest_task_id),
    )
    return int(cur.lastrowid)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    loaded: int,
    applied: int,
    quarantined: int,
    skipped: int,
    cursor_after: int,
    report: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE apply_runs SET status=?, loaded_count=?, applied_count=?, quarantined_count=?,
            skipped_count=?, cursor_after=?, report_json=? WHERE id=?
        """,
        (
            status,
            loaded,
            applied,
            quarantined,
            skipped,
            cursor_after,
            json.dumps(report, ensure_ascii=False),
            run_id,
        ),
    )


def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["report"] = json.loads(item.pop("report_json") or "{}")
    return item


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, stream_id, status, loaded_count, applied_count, quarantined_count, skipped_count,
               cursor_before, cursor_after, report_json, created_at, harvest_task_id
        FROM apply_runs ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_row_to_run(r) for r in rows]


def get_run(conn: sqlite3.Connection, run_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, stream_id, status, loaded_count, applied_count, quarantined_count, skipped_count,
               cursor_before, cursor_after, report_json, created_at, harvest_task_id
        FROM apply_runs WHERE id=?
        """,
        (run_id,),
    ).fetchone()
    return _row_to_run(row) if row else None


def runs_for_task(conn: sqlite3.Connection, task_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, stream_id, status, loaded_count, applied_count, quarantined_count, skipped_count,
               cursor_before, cursor_after, report_json, created_at, harvest_task_id
        FROM apply_runs WHERE harvest_task_id=? ORDER BY id
        """,
        (task_id,),
    ).fetchall()
    return [_row_to_run(r) for r in rows]
