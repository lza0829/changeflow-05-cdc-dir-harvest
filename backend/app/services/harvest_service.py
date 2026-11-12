from __future__ import annotations

from typing import Any

from app.db import connect
from app.engines.harvest_scan import HarvestPathError, resolve_source_dir, scan_shards
from app.engines.parse_change import parse_change_text
from app.repositories import harvest as harvest_repo
from app.repositories import ledger as ledger_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import sink as sink_repo
from app.repositories import streams as streams_repo


def _get_task(conn, task_id: int) -> dict[str, Any]:
    task = harvest_repo.get_task(conn, task_id)
    if not task:
        raise ValueError("harvest task not found")
    return task


def harvest_task_detail(conn, task_id: int) -> dict[str, Any]:
    """任务报告 + 分片清单 + 账本处置 + Apply/Sink/游标 delta，全部同源。"""
    task = _get_task(conn, task_id)
    shards = harvest_repo.list_shards(conn, task_id)
    shard_counts = harvest_repo.shard_status_counts(conn, task_id)
    dispositions = ledger_repo.disposition_counts_for_task(conn, task_id)
    ledger_total = sum(dispositions.values())
    runs = runs_repo.runs_for_task(conn, task_id)
    stream = streams_repo.get_stream(conn, task["stream_id"])

    collected = shard_counts.get("collected", 0)
    skipped = shard_counts.get("skipped_duplicate", 0)
    failed = shard_counts.get("failed", 0)
    collected_events = sum(s["event_count"] for s in shards if s["status"] == "collected")

    applied = dispositions.get("applied", 0)
    quarantined = dispositions.get("quarantine_gap", 0)
    dup = dispositions.get("skipped_duplicate", 0)
    not_yet_applied = dispositions.get("collected", 0)

    applies = [
        {
            "run_id": r["id"],
            "status": r["status"],
            "loaded": r["loaded_count"],
            "applied": r["applied_count"],
            "quarantined": r["quarantined_count"],
            "skipped": r["skipped_count"],
            "cursor_before": r["cursor_before"],
            "cursor_after": r["cursor_after"],
            "sink_delta": r["report"].get("sink_delta"),
            "pending_not_applied": r["report"].get("pending_not_applied", 0),
            "created_at": r["created_at"],
        }
        for r in runs
    ]

    checks = {
        "shard_statuses_sum_to_discovered": (collected + skipped + failed)
        == task["discovered_count"]
        == len(shards),
        "collected_events_match_task_report": collected_events == task["event_count"],
        "collected_events_match_ledger": collected_events == ledger_total,
        "ledger_dispositions_sum_to_ledger": (
            applied + quarantined + dup + not_yet_applied == ledger_total
        ),
        "apply_counts_sum_to_loaded": all(
            a["applied"] + a["quarantined"] + a["skipped"] + a["pending_not_applied"]
            == a["loaded"]
            for a in applies
        ),
    }
    return {
        "task": task,
        "shards": shards,
        "reconciliation": {
            "discovered_files": task["discovered_count"],
            "collected_files": collected,
            "skipped_files": skipped,
            "failed_files": failed,
            "collected_events": collected_events,
            "ledger_events": ledger_total,
            "ledger_dispositions": dispositions,
            "applied": applied,
            "quarantined": quarantined,
            "skipped_duplicate": dup,
            "not_yet_applied": not_yet_applied,
            "apply_runs": applies,
            "stream_cursor_after": stream["apply_cursor"] if stream else None,
            "sink_rows_for_stream": sink_repo.count_sink_for_stream(
                conn, task["stream_id"]
            ),
            "sink_delta_from_runs": sum(
                (a["sink_delta"] or 0) for a in applies
            ),
            "checks": checks,
            "balanced": all(checks.values()),
        },
    }


def harvest_detail(task_id: int) -> dict[str, Any]:
    conn = connect()
    try:
        return harvest_task_detail(conn, task_id)
    finally:
        conn.close()


def run_harvest(
    *,
    source_dir: str,
    stream_id: int | None = None,
    auto_apply: bool = True,
) -> dict[str, Any]:
    """巡检本机目录 → 生成采集任务与分片清单 → 分片事件入账（不写 Sink）。

    采集只做「发现 + 去重 + 解析 + 入账」。应用由现有 Apply 引擎从账本拉取，
    因而连续序 / 幂等 / 隔离规则完全复用，不会绕过隔离直接写 Sink。
    """
    conn = connect()
    try:
        stream = streams_repo.get_stream(conn, stream_id) if stream_id else None
        if stream is None:
            row = conn.execute(
                "SELECT id FROM streams WHERE entity_type='harvest' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                raise ValueError("harvest stream not configured")
            stream = streams_repo.get_stream(conn, int(row["id"]))
        if not stream:
            raise ValueError("stream not found")
        if not stream["enabled"]:
            raise ValueError("stream disabled")
        if stream["entity_type"] != "harvest":
            raise ValueError("指定流不是采集流；请选择 Harvest CDC 采集流")

        try:
            resolved_dir = resolve_source_dir(source_dir)
        except HarvestPathError as exc:
            raise ValueError(str(exc)) from exc

        task_id = harvest_repo.create_task(
            conn, source_dir=str(resolved_dir), stream_id=int(stream["id"])
        )
        settings_repo.put(conn, "harvest_source_dir", str(resolved_dir))
        collected = 0
        skipped = 0
        failed = 0
        event_count = 0
        task_sha_seen: dict[str, int] = {}
        task_seq_seen: set[int] = set()
        shard_notes: list[dict[str, Any]] = []

        try:
            scanned = scan_shards(resolved_dir)
        except Exception as exc:  # noqa: BLE001
            harvest_repo.finish_task(
                conn,
                task_id,
                status="failed",
                discovered=0,
                success=0,
                skipped=0,
                failed=0,
                event_count=0,
                report={"error": str(exc), "source_dir": str(resolved_dir)},
            )
            conn.commit()
            return harvest_task_detail(conn, task_id)

        for shard in scanned:
            same_task_dup = task_sha_seen.get(shard.sha256)
            prior = harvest_repo.find_prior_shard_by_sha(
                conn,
                sha256=shard.sha256,
                exclude_task_id=task_id,
                stream_id=int(stream["id"]),
            )
            if same_task_dup is not None or prior is not None:
                duplicate_of = same_task_dup if same_task_dup is not None else int(prior["id"])
                harvest_repo.insert_shard(
                    conn,
                    task_id=task_id,
                    filename=shard.filename,
                    rel_path=shard.rel_path,
                    sha256=shard.sha256,
                    size_bytes=shard.size_bytes,
                    status="skipped_duplicate",
                    event_count=int((prior or {}).get("event_count") or 0),
                    reason=(
                        "same_content_in_same_task"
                        if same_task_dup is not None
                        else "same_content_already_collected"
                    ),
                    duplicate_of=duplicate_of,
                )
                shard_notes.append(
                    {
                        "path": shard.rel_path,
                        "status": "skipped_duplicate",
                        "duplicate_of_shard": duplicate_of,
                    }
                )
                skipped += 1
                continue

            same_name = harvest_repo.find_prior_shard_by_name(
                conn,
                rel_path=shard.rel_path,
                exclude_task_id=task_id,
                stream_id=int(stream["id"]),
            )

            try:
                events = parse_change_text(
                    shard.path.read_text(encoding="utf-8"), source=shard.rel_path
                )
            except (OSError, ValueError) as exc:
                harvest_repo.insert_shard(
                    conn,
                    task_id=task_id,
                    filename=shard.filename,
                    rel_path=shard.rel_path,
                    sha256=shard.sha256,
                    size_bytes=shard.size_bytes,
                    status="failed",
                    reason=f"parse_error: {exc}",
                )
                shard_notes.append(
                    {"path": shard.rel_path, "status": "failed", "reason": "parse_error"}
                )
                failed += 1
                continue

            if not events:
                harvest_repo.insert_shard(
                    conn,
                    task_id=task_id,
                    filename=shard.filename,
                    rel_path=shard.rel_path,
                    sha256=shard.sha256,
                    size_bytes=shard.size_bytes,
                    status="failed",
                    reason="empty_shard",
                )
                shard_notes.append(
                    {"path": shard.rel_path, "status": "failed", "reason": "empty_shard"}
                )
                failed += 1
                continue

            first_seq = int(events[0]["seq"])
            last_shard_seq = int(events[-1]["seq"])
            # 同一采集批次内 seq 不得跨分片重复（例如重新切分导致同一事件出现在两片）。
            shard_seqs = {int(e["seq"]) for e in events}
            overlap = sorted(shard_seqs & task_seq_seen)
            if overlap:
                harvest_repo.insert_shard(
                    conn,
                    task_id=task_id,
                    filename=shard.filename,
                    rel_path=shard.rel_path,
                    sha256=shard.sha256,
                    size_bytes=shard.size_bytes,
                    status="failed",
                    event_count=len(events),
                    first_seq=first_seq,
                    last_seq=last_shard_seq,
                    reason=f"seq_overlap_in_batch: {overlap[0]}..{overlap[-1]}",
                )
                shard_notes.append(
                    {"path": shard.rel_path, "status": "failed", "reason": "seq_overlap_in_batch"}
                )
                failed += 1
                continue
            task_seq_seen.update(shard_seqs)
            shard_id = harvest_repo.insert_shard(
                conn,
                task_id=task_id,
                filename=shard.filename,
                rel_path=shard.rel_path,
                sha256=shard.sha256,
                size_bytes=shard.size_bytes,
                status="collected",
                event_count=len(events),
                first_seq=first_seq,
                last_seq=last_shard_seq,
                reason="same_name_new_content" if same_name else None,
            )
            task_sha_seen[shard.sha256] = shard_id
            for event in events:
                ledger_repo.insert_ledger(
                    conn,
                    stream_id=int(stream["id"]),
                    run_id=None,
                    event=event,
                    disposition="collected",
                    harvest_task_id=task_id,
                    harvest_shard_id=shard_id,
                )
            event_count += len(events)
            collected += 1
            shard_notes.append(
                {
                    "path": shard.rel_path,
                    "status": "collected",
                    "events": len(events),
                    "seq": [first_seq, last_shard_seq],
                    "same_name_prior_content": same_name is not None,
                }
            )

        # 状态判定：发现 0 个分片 → empty；有失败但无成功 → failed；有成功但有失败 → partial；
        # 全部跳过（重复巡检）仍算 succeeded（去重是预期行为，失败数为 0）。
        if not scanned:
            status = "empty"
        elif failed == 0:
            status = "succeeded"
        elif collected == 0:
            status = "failed"
        else:
            status = "partial"
        report = {
            "source_dir": str(resolved_dir),
            "shard_notes": shard_notes,
            "dupe_policy": settings_repo.get(
                conn, "harvest_dupe_policy", "skip_duplicate_shard"
            ),
        }
        harvest_repo.finish_task(
            conn,
            task_id,
            status=status,
            discovered=len(scanned),
            success=collected,
            skipped=skipped,
            failed=failed,
            event_count=event_count,
            report=report,
        )
        conn.commit()

        if auto_apply and event_count > 0:
            from app.services.apply_service import run_apply_from_harvest

            run = run_apply_from_harvest(
                stream_id=int(stream["id"]), harvest_task_id=task_id
            )
            harvest_repo.set_apply_run(conn, task_id, int(run["id"]))
            # 采集成功但应用因缺口中止时，任务整体标记 partial，避免误报成功。
            if status == "succeeded" and run["status"] != "succeeded":
                conn.execute(
                    "UPDATE harvest_tasks SET status=? WHERE id=?", ("partial", task_id)
                )
            conn.commit()
        return harvest_task_detail(conn, task_id)
    finally:
        conn.close()
