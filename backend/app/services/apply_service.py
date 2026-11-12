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
        path = FIXTURES_DIR / stream["fixture_path"]
        events = parse_change_fixture(path)
        return {"stream": stream, "count": len(events), "events": events[:50]}
    finally:
        conn.close()


def run_apply(stream_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        stream = streams_repo.get_stream(conn, stream_id)
        if not stream:
            raise ValueError("stream not found")
        if not stream["enabled"]:
            raise ValueError("stream disabled")

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

        loaded = len(events)
        applied = 0
        quarantined = 0
        skipped = 0
        cursor = cursor_before
        dispositions: list[str] = []
        stopped = False

        for event in events:
            already = cursor_repo.is_applied(conn, stream_id, int(event["seq"]))
            decision = classify_event(
                event=event,
                cursor=cursor,
                already_applied=already,
                gap_policy=gap_policy,
            )

            if decision == "skipped_duplicate":
                ledger_repo.insert_ledger(
                    conn, stream_id=stream_id, run_id=run_id, event=event, disposition=decision
                )
                skipped += 1
                dispositions.append(decision)
                continue

            if decision == "quarantine_gap":
                ledger_repo.insert_ledger(
                    conn, stream_id=stream_id, run_id=run_id, event=event, disposition=decision
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
                break

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
            ledger_repo.insert_ledger(
                conn, stream_id=stream_id, run_id=run_id, event=event, disposition="applied"
            )
            applied += 1
            dispositions.append("applied")

        status = "partial" if stopped else "succeeded"
        report = {
            "stream_id": stream_id,
            "gap_policy": gap_policy,
            "dispositions": dispositions,
            "stopped_on_gap": stopped,
            "sink_count_after": sink_repo.count_sink(conn),
            "quarantine_count_after": quarantine_repo.count_quarantine(conn),
        }
        runs_repo.finish_run(
            conn,
            run_id,
            status=status,
            loaded=loaded,
            applied=applied,
            quarantined=quarantined,
            skipped=skipped,
            cursor_after=cursor,
            report=report,
        )
        conn.commit()
        return runs_repo.get_run(conn, run_id) or {}
    finally:
        conn.close()
