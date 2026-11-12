"""采集 → 入账 → 应用 → 对账 的端到端校验（使用临时 DATA_DIR）。"""
from __future__ import annotations


def _harvest_stream_id(c):
    streams = c.get("/api/streams").json()
    for s in streams:
        if s["entity_type"] == "harvest":
            return s["id"]
    raise AssertionError("harvest stream missing")


def test_harvest_demo_end_to_end(client):
    stream_id = _harvest_stream_id(client)
    resp = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "harvest_demo", "stream_id": stream_id, "auto_apply": True},
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    task = detail["task"]
    rec = detail["reconciliation"]

    assert task["status"] == "succeeded"
    assert task["discovered_count"] == 3
    assert task["success_count"] == 3
    assert task["skipped_count"] == 0
    assert task["failed_count"] == 0
    assert task["event_count"] == 8

    assert rec["collected_events"] == 8
    assert rec["ledger_events"] == 8
    assert rec["applied"] == 8
    assert rec["quarantined"] == 0
    assert rec["not_yet_applied"] == 0
    assert rec["balanced"] is True, rec

    runs = rec["apply_runs"]
    assert len(runs) == 1
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["applied"] == 8
    assert runs[0]["cursor_after"] == 8

    # Sink：8 个事件中 seq5 删除 CUST-3002，因此该流 Sink 行数 = 唯一 upsert 实体数。
    sink = client.get("/api/sink").json()
    harvest_rows = [r for r in sink if r["stream_id"] == stream_id]
    keys = {r["entity_key"] for r in harvest_rows}
    assert keys == {"CUST-3001", "CUST-3003", "CUST-3004", "CUST-3005"}
    assert rec["sink_rows_for_stream"] == len(harvest_rows)

    cursors = c_get_cursor(client, stream_id)
    assert cursors["apply_cursor"] == 8
    assert cursors["applied_seq_count"] == 8
    assert cursors["max_applied_seq"] == 8


def c_get_cursor(client, stream_id):
    for row in client.get("/api/cursors").json():
        if row["stream_id"] == stream_id:
            return row
    raise AssertionError("cursor row missing")


def test_rerun_same_dir_skips_duplicates_and_does_not_touch_sink(client):
    stream_id = _harvest_stream_id(client)
    first = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "harvest_demo", "stream_id": stream_id, "auto_apply": True},
    ).json()
    assert first["task"]["status"] == "succeeded"
    assert first["reconciliation"]["applied"] == 8
    first_task_id = first["task"]["id"]
    first_run_id = first["task"]["apply_run_id"]
    second = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "harvest_demo", "stream_id": stream_id, "auto_apply": True},
    ).json()

    task2 = second["task"]
    rec2 = second["reconciliation"]
    assert task2["discovered_count"] == 3
    assert task2["success_count"] == 0
    assert task2["skipped_count"] == 3
    assert task2["failed_count"] == 0
    assert task2["event_count"] == 0
    assert rec2["ledger_events"] == 0
    assert rec2["applied"] == 0
    assert rec2["balanced"] is True, rec2
    # 记录去重来源，不是无记录地当新成功。
    shards = second["shards"]
    assert all(s["status"] == "skipped_duplicate" for s in shards)
    assert all(s["duplicate_of"] for s in shards)

    # 重复巡检不应生成 Apply run，也不改 Sink / 游标；原任务与 run 仍保留且可追溯。
    assert second["reconciliation"]["apply_runs"] == []
    assert task2["apply_run_id"] is None
    assert first_run_id is not None
    prior = client.get(f"/api/harvest/tasks/{first_task_id}").json()
    assert prior["task"]["apply_run_id"] == first_run_id
    assert prior["reconciliation"]["applied"] == 8
    # 全部已应用后再对原任务重试，不应产生空跑 run。
    retried = client.post(
        f"/api/harvest/tasks/{first_task_id}/apply", json={}
    ).json()
    assert len(retried["reconciliation"]["apply_runs"]) == 1
    sink_after = [
        r for r in client.get("/api/sink").json() if r["stream_id"] == stream_id
    ]
    assert len(sink_after) == 4
    assert c_get_cursor(client, stream_id)["apply_cursor"] == 8


def test_partial_failure_is_reported(client):
    stream_id = _harvest_stream_id(client)
    detail = client.post(
        "/api/harvest/tasks",
        json={
            "source_dir": "harvest_demo_mixed",
            "stream_id": stream_id,
            "auto_apply": True,
        },
    ).json()
    task = detail["task"]
    rec = detail["reconciliation"]
    assert task["status"] == "failed"
    assert task["discovered_count"] == 3
    assert task["success_count"] == 0
    assert task["failed_count"] == 3
    assert rec["balanced"] is True, rec


def test_task_persists_after_reload(client):
    stream_id = _harvest_stream_id(client)
    created = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "harvest_demo", "stream_id": stream_id, "auto_apply": True},
    ).json()
    task_id = created["task"]["id"]
    # 新 client / 新连接读取同一 SQLite 文件（刷新等价）。
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as fresh:
        again = fresh.get(f"/api/harvest/tasks/{task_id}")
    assert again.status_code == 200
    assert again.json()["task"]["id"] == task_id
    assert again.json()["task"]["status"] == "succeeded"
    listed = client.get("/api/harvest/tasks").json()
    assert any(t["id"] == task_id for t in listed)


def test_gap_shard_quarantines_and_stops_without_writing_sink(client):
    stream_id = _harvest_stream_id(client)
    detail = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "harvest_demo_gap", "stream_id": stream_id, "auto_apply": True},
    ).json()
    task = detail["task"]
    rec = detail["reconciliation"]
    # seq 1,3 → 缺 2，采集成功但应用在缺口停 → 任务整体 partial。
    assert task["status"] == "partial"
    assert task["discovered_count"] == 2
    assert task["success_count"] == 2
    assert task["event_count"] == 3
    assert rec["applied"] == 1
    assert rec["quarantined"] == 1
    assert rec["not_yet_applied"] == 1
    assert rec["balanced"] is True, rec
    assert rec["apply_runs"][0]["status"] == "partial"
    sink_for_stream = rec["sink_rows_for_stream"]
    assert sink_for_stream == 1
    # 隔离区确实有该任务的记录（未绕过隔离直接写 Sink）。
    q = [r for r in client.get("/api/quarantine").json() if r["stream_id"] == stream_id]
    assert len(q) == 1
    assert q[0]["seq"] == 3

    # 缺口补齐：新增包含缺失 seq 2 的分片（新内容，非重复），应用继续推进。
    supplement = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "harvest_demo_gap_fill", "stream_id": stream_id, "auto_apply": True},
    ).json()
    after = supplement["reconciliation"]
    assert supplement["task"]["event_count"] == 1
    assert after["applied"] == 1
    assert after["not_yet_applied"] == 0
    assert after["balanced"] is True, after
    cursor = [c for c in client.get("/api/cursors").json() if c["stream_id"] == stream_id][0]
    assert cursor["apply_cursor"] == 2
    # 上一任务中因缺口被隔离的 seq 3 仍留在账本 quarantine_gap，需人工处置，不会被静默重写。
    old = client.get("/api/harvest/tasks/1").json()
    assert old["reconciliation"]["ledger_dispositions"]["quarantine_gap"] == 1


def test_empty_dir_reports_empty_and_balanced(client):
    stream_id = _harvest_stream_id(client)
    detail = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "harvest_demo_empty", "stream_id": stream_id, "auto_apply": True},
    ).json()
    task = detail["task"]
    assert task["status"] == "empty"
    assert task["discovered_count"] == 0
    assert task["event_count"] == 0
    assert detail["reconciliation"]["balanced"] is True
    assert detail["reconciliation"]["apply_runs"] == []


def test_reject_non_harvest_stream(client):
    orders = [s for s in client.get("/api/streams").json() if s["entity_type"] == "order"][0]
    resp = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "harvest_demo", "stream_id": orders["id"], "auto_apply": True},
    )
    assert resp.status_code == 400
    assert "不是采集流" in resp.text or "harvest" in resp.text


def test_reject_outside_root(client):
    resp = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "/etc", "auto_apply": True},
    )
    assert resp.status_code == 400
    assert "outside allowed" in resp.text


def test_cross_shard_seq_overlap_is_rejected(client):
    stream_id = _harvest_stream_id(client)
    detail = client.post(
        "/api/harvest/tasks",
        json={"source_dir": "harvest_demo_overlap", "stream_id": stream_id, "auto_apply": True},
    ).json()
    task = detail["task"]
    rec = detail["reconciliation"]
    # a.jsonl 收 seq1-2；b.jsonl 与 a 重叠 seq2 → 拒收，避免同批重复入账。
    assert task["discovered_count"] == 2
    assert task["success_count"] == 1
    assert task["event_count"] == 2
    assert task["failed_count"] == 1
    assert task["status"] == "partial"
    overlap = [s for s in detail["shards"] if s["status"] == "failed"][0]
    assert "seq_overlap_in_batch" in overlap["reason"]
    assert rec["balanced"] is True, rec
    assert rec["applied"] == 2


def test_fixture_flow_still_works_after_harvest(client):
    orders = [s for s in client.get("/api/streams").json() if s["entity_type"] == "order"][0]
    run = client.post("/api/apply", json={"stream_id": orders["id"]}).json()
    assert run["status"] == "succeeded"
    assert run["applied_count"] == 5
    assert run["cursor_after"] == 5
    assert run["harvest_task_id"] is None
