from __future__ import annotations

from typing import Any

from app.config import FIXTURES_DIR
from app.db import connect
from app.engines.apply_rules import classify_event
from app.engines.parse_change import parse_change_fixture
from app.repositories import cursors as cursor_repo
from app.repositories import ledger as ledger_repo
from app.repositories import quarantine as quarantine_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import sink as sink_repo
from app.repositories import streams as streams_repo


def preview_stream(stream_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        stream = streams_repo.get_stream(conn, stream_id)
        if not stream:
            raise ValueError("stream not found")
        if not stream["fixture_path"]:
            raise ValueError("stream has no fixture; it is fed by harvest tasks")
        path = FIXTURES_DIR / stream["fixture_path"]
        events = parse_change_fixture(path)
        return {"stream": stream, "count": len(events), "events": events[:50]}
    finally:
        conn.close()


def _apply_events(
    conn,
    *,
    stream_id: int,
    run_id: int,
    events: list[dict[str, Any]],
    cursor_before: int,
    gap_policy: str,
    harvest_task_id: int | None = None,
    source: str = "fixture",
) -> dict[str, Any]:
    """连续序 / 缺口隔离 / 幂等跳过 —— fixture 路径与采集账本路径共用同一裁决。

    events 可以是已解析夹具，也可以是采集任务在账本中的 collected 事件；
    每次 Apply 都会重新查询 applied_seqs，重复事件只记 skipped_duplicate。
    """
    applied = 0
    quarantined = 0
    skipped = 0
    cursor = cursor_before
    dispositions: list[str] = []
    stopped = False
    sink_before = sink_repo.count_sink_for_stream(conn, stream_id)
    pending = list(events)

    for index, event in enumerate(pending):
        ledger_row_id = event.get("_ledger_id")
        already = cursor_repo.is_applied(conn, stream_id, int(event["seq"])) or bool(
            event.get("_already_applied")
        )
        decision = classify_event(
            event=event,
            cursor=cursor,
            already_applied=already,
            gap_policy=gap_policy,
        )

        if decision == "skipped_duplicate":
            if ledger_row_id is not None:
                ledger_repo.set_disposition(
                    conn, int(ledger_row_id), disposition=decision, run_id=run_id
                )
            else:
                ledger_repo.insert_ledger(
                    conn,
                    stream_id=stream_id,
                    run_id=run_id,
                    event=event,
                    disposition=decision,
                    harvest_task_id=harvest_task_id,
                )
            skipped += 1
            dispositions.append(decision)
            continue

        if decision == "quarantine_gap":
            if ledger_row_id is not None:
                ledger_repo.set_disposition(
                    conn, int(ledger_row_id), disposition=decision, run_id=run_id
                )
            else:
                ledger_repo.insert_ledger(
                    conn,
                    stream_id=stream_id,
                    run_id=run_id,
                    event=event,
                    disposition=decision,
                    harvest_task_id=harvest_task_id,
                )
            quarantine_repo.insert(
                conn,
                stream_id=stream_id,
                run_id=run_id,
                seq=int(event["seq"]),
                entity_key=event["entity_key"],
                reason="gap_before_seq",
                payload=event.get("payload") or {},
            )
            quarantined += 1
            dispositions.append(decision)
            stopped = True
            break  # 缺口停：后续事件保持 pending（采集事件仍在账本 collected）

        # apply
        if event["op"] == "upsert":
            sink_repo.upsert(
                conn,
                stream_id=stream_id,
                entity_key=event["entity_key"],
                payload=event.get("payload") or {},
                seq=int(event["seq"]),
                event_ts=event["event_ts"],
            )
        else:
            sink_repo.delete(conn, stream_id=stream_id, entity_key=event["entity_key"])

        cursor_repo.mark_applied(conn, stream_id, int(event["seq"]), run_id)
        cursor = int(event["seq"])
        streams_repo.set_cursor(conn, stream_id, cursor)
        if ledger_row_id is not None:
            ledger_repo.set_disposition(
                conn, int(ledger_row_id), disposition="applied", run_id=run_id
            )
        else:
            ledger_repo.insert_ledger(
                conn,
                stream_id=stream_id,
                run_id=run_id,
                event=event,
                disposition="applied",
                harvest_task_id=harvest_task_id,
            )
        applied += 1
        dispositions.append("applied")

    remaining = 0
    if stopped:
        remaining = len(pending) - (index + 1)

    sink_after = sink_repo.count_sink_for_stream(conn, stream_id)
    status = "partial" if stopped else "succeeded"
    report = {
        "stream_id": stream_id,
        "source": source,
        "gap_policy": gap_policy,
        "dispositions": dispositions,
        "stopped_on_gap": stopped,
        "pending_not_applied": remaining,
        "ledger_events_in_run": ledger_repo.count_for_run(conn, run_id),
        "sink_count_after": sink_repo.count_sink(conn),
        "sink_count_for_stream_after": sink_after,
        "sink_delta": sink_after - sink_before,
        "quarantine_count_after": quarantine_repo.count_quarantine(conn),
    }
    if harvest_task_id is not None:
        report["harvest_task_id"] = harvest_task_id
    runs_repo.finish_run(
        conn,
        run_id,
        status=status,
        loaded=len(pending),
        applied=applied,
        quarantined=quarantined,
        skipped=skipped,
        cursor_after=cursor,
        report=report,
    )
    return report


def run_apply(stream_id: int) -> dict[str, Any]:
    """从流的夹具文件应用（原有主链）。"""
    conn = connect()
    try:
        stream = streams_repo.get_stream(conn, stream_id)
        if not stream:
            raise ValueError("stream not found")
        if not stream["enabled"]:
            raise ValueError("stream disabled")
        if not stream["fixture_path"]:
            raise ValueError(
                "stream has no fixture; run Apply through a harvest task"
            )

        cursor_before = int(stream["apply_cursor"] or 0)
        gap_policy = settings_repo.get(conn, "gap_policy", "stop_quarantine") or "stop_quarantine"
        run_id = runs_repo.create_run(conn, stream_id, cursor_before)
        path = FIXTURES_DIR / stream["fixture_path"]

        try:
            events = parse_change_fixture(path)
        except Exception as exc:  # noqa: BLE001
            runs_repo.finish_run(
                conn,
                run_id,
                status="failed",
                loaded=0,
                applied=0,
                quarantined=0,
                skipped=0,
                cursor_after=cursor_before,
                report={"error": str(exc)},
            )
            conn.commit()
            raise

        _apply_events(
            conn,
            stream_id=stream_id,
            run_id=run_id,
            events=events,
            cursor_before=cursor_before,
            gap_policy=gap_policy,
            source="fixture",
        )
        conn.commit()
        return runs_repo.get_run(conn, run_id) or {}
    finally:
        conn.close()


def run_apply_from_harvest(*, stream_id: int, harvest_task_id: int) -> dict[str, Any]:
    """把某次采集任务已入账（collected）的事件按连续序应用到 Sink。

    - 只消费本任务 disposition='collected' 的账本行，应用到哪条就改写哪条的 disposition；
    - 中途缺口停止时，其余行保持 collected，可在后续采集/重试时继续；
    - applied_seqs 全局去重，重放同内容分片不会重复写 Sink。
    """
    conn = connect()
    try:
        stream = streams_repo.get_stream(conn, stream_id)
        if not stream:
            raise ValueError("stream not found")
        if not stream["enabled"]:
            raise ValueError("stream disabled")

        cursor_before = int(stream["apply_cursor"] or 0)
        gap_policy = settings_repo.get(conn, "gap_policy", "stop_quarantine") or "stop_quarantine"

        pending_rows = ledger_repo.pending_for_task(conn, harvest_task_id)
        events: list[dict[str, Any]] = []
        for row in pending_rows:
            events.append(
                {
                    "seq": int(row["seq"]),
                    "op": row["op"],
                    "entity_key": row["entity_key"],
                    "event_ts": row["event_ts"],
                    "payload": row.get("payload") or {},
                    "_ledger_id": int(row["id"]),
                }
            )

        # 没有待应用事件时直接返回「上一次本任务 Apply run」，避免产生空跑记录。
        if not events:
            prior = runs_repo.runs_for_task(conn, harvest_task_id)
            if prior:
                return prior[-1]
            return {
                "id": None,
                "stream_id": stream_id,
                "status": "noop",
                "loaded_count": 0,
                "applied_count": 0,
                "quarantined_count": 0,
                "skipped_count": 0,
                "cursor_before": cursor_before,
                "cursor_after": cursor_before,
                "harvest_task_id": harvest_task_id,
                "created_at": None,
                "report": {
                    "stream_id": stream_id,
                    "source": "harvest",
                    "harvest_task_id": harvest_task_id,
                    "note": "no collected events pending",
                    "sink_delta": 0,
                },
            }

        run_id = runs_repo.create_run(
            conn, stream_id, cursor_before, harvest_task_id=harvest_task_id
        )
        _apply_events(
            conn,
            stream_id=stream_id,
            run_id=run_id,
            events=events,
            cursor_before=cursor_before,
            gap_policy=gap_policy,
            harvest_task_id=harvest_task_id,
            source="harvest",
        )
        conn.commit()
        return runs_repo.get_run(conn, run_id) or {}
    finally:
        conn.close()
