from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_task(conn: sqlite3.Connection, *, source_dir: str, stream_id: int) -> int:
    cur = conn.execute(
        """
        INSERT INTO harvest_tasks(source_dir, stream_id, status, created_at)
        VALUES (?,?,?,?)
        """,
        (source_dir, stream_id, "running", _now()),
    )
    return int(cur.lastrowid)


def insert_shard(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    filename: str,
    rel_path: str,
    sha256: str,
    size_bytes: int,
    status: str,
    event_count: int = 0,
    first_seq: int | None = None,
    last_seq: int | None = None,
    reason: str | None = None,
    duplicate_of: int | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO harvest_shards(
            task_id, filename, rel_path, sha256, size_bytes, event_count, first_seq, last_seq,
            status, reason, duplicate_of, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            task_id,
            filename,
            rel_path,
            sha256,
            size_bytes,
            event_count,
            first_seq,
            last_seq,
            status,
            reason,
            duplicate_of,
            _now(),
        ),
    )
    return int(cur.lastrowid)


def update_shard(
    conn: sqlite3.Connection,
    shard_id: int,
    *,
    status: str,
    event_count: int | None = None,
    first_seq: int | None = None,
    last_seq: int | None = None,
    reason: str | None = None,
    duplicate_of: int | None = None,
) -> None:
    conn.execute(
        """
        UPDATE harvest_shards SET status=?, event_count=?, first_seq=?, last_seq=?,
            reason=?, duplicate_of=? WHERE id=?
        """,
        (status, event_count, first_seq, last_seq, reason, duplicate_of, shard_id),
    )


def finish_task(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    status: str,
    discovered: int,
    success: int,
    skipped: int,
    failed: int,
    event_count: int,
    report: dict[str, Any],
    apply_run_id: int | None = None,
) -> None:
    conn.execute(
        """
        UPDATE harvest_tasks SET status=?, discovered_count=?, success_count=?, skipped_count=?,
            failed_count=?, event_count=?, apply_run_id=?, report_json=?, finished_at=?
        WHERE id=?
        """,
        (
            status,
            discovered,
            success,
            skipped,
            failed,
            event_count,
            apply_run_id,
            json.dumps(report, ensure_ascii=False),
            _now(),
            task_id,
        ),
    )


def set_apply_run(conn: sqlite3.Connection, task_id: int, run_id: int) -> None:
    conn.execute("UPDATE harvest_tasks SET apply_run_id=? WHERE id=?", (run_id, task_id))


def _row_to_task(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["report"] = json.loads(item.pop("report_json") or "{}")
    return item


def list_tasks(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, source_dir, stream_id, status, discovered_count, success_count, skipped_count,
               failed_count, event_count, apply_run_id, report_json, created_at, finished_at
        FROM harvest_tasks ORDER BY id DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_row_to_task(r) for r in rows]


def get_task(conn: sqlite3.Connection, task_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, source_dir, stream_id, status, discovered_count, success_count, skipped_count,
               failed_count, event_count, apply_run_id, report_json, created_at, finished_at
        FROM harvest_tasks WHERE id=?
        """,
        (task_id,),
    ).fetchone()
    return _row_to_task(row) if row else None


def list_shards(conn: sqlite3.Connection, task_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, task_id, filename, rel_path, sha256, size_bytes, event_count, first_seq,
               last_seq, status, reason, duplicate_of, created_at
        FROM harvest_shards WHERE task_id=? ORDER BY rel_path, id
        """,
        (task_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def shard_status_counts(conn: sqlite3.Connection, task_id: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) c FROM harvest_shards WHERE task_id=? GROUP BY status",
        (task_id,),
    ).fetchall()
    return {r["status"]: int(r["c"]) for r in rows}


def find_prior_shard_by_sha(
    conn: sqlite3.Connection, *, sha256: str, exclude_task_id: int, stream_id: int
) -> dict[str, Any] | None:
    """查找同流此前已成功入账的同内容分片（跨任务、按内容 sha 去重）。"""
    row = conn.execute(
        """
        SELECT hs.id, hs.task_id, hs.filename, hs.rel_path, hs.sha256, hs.status, hs.event_count
        FROM harvest_shards hs
        JOIN harvest_tasks ht ON ht.id = hs.task_id
        WHERE hs.sha256=? AND hs.status='collected' AND hs.task_id<>? AND ht.stream_id=?
        ORDER BY hs.id LIMIT 1
        """,
        (sha256, exclude_task_id, stream_id),
    ).fetchone()
    return dict(row) if row else None


def find_prior_shard_by_name(
    conn: sqlite3.Connection, *, rel_path: str, exclude_task_id: int, stream_id: int
) -> dict[str, Any] | None:
    """同相对路径再次出现且内容已变化时，用于提示「同名新内容」。"""
    row = conn.execute(
        """
        SELECT hs.id, hs.task_id, hs.filename, hs.rel_path, hs.sha256, hs.status, hs.event_count
        FROM harvest_shards hs
        JOIN harvest_tasks ht ON ht.id = hs.task_id
        WHERE hs.rel_path=? AND hs.task_id<>? AND hs.status='collected' AND ht.stream_id=?
        ORDER BY hs.id DESC LIMIT 1
        """,
        (rel_path, exclude_task_id, stream_id),
    ).fetchone()
    return dict(row) if row else None
