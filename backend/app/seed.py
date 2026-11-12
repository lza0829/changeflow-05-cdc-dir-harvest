from app.db import connect


# 采集任务 / 分片清单：与 apply_runs、change_ledger 同库持久化，刷新后仍可查。
SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS streams(
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    fixture_path TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    apply_cursor INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    note TEXT
);
CREATE TABLE IF NOT EXISTS apply_runs(
    id INTEGER PRIMARY KEY,
    stream_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    loaded_count INTEGER NOT NULL,
    applied_count INTEGER NOT NULL,
    quarantined_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    cursor_before INTEGER NOT NULL,
    cursor_after INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    harvest_task_id INTEGER
);
CREATE TABLE IF NOT EXISTS change_ledger(
    id INTEGER PRIMARY KEY,
    stream_id INTEGER NOT NULL,
    run_id INTEGER,
    seq INTEGER NOT NULL,
    op TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    event_ts TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    disposition TEXT NOT NULL,
    harvest_task_id INTEGER,
    harvest_shard_id INTEGER,
    UNIQUE(stream_id, seq, run_id)
);
CREATE TABLE IF NOT EXISTS sink_records(
    id INTEGER PRIMARY KEY,
    stream_id INTEGER NOT NULL,
    entity_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    last_seq INTEGER NOT NULL,
    last_event_ts TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(stream_id, entity_key)
);
CREATE TABLE IF NOT EXISTS quarantine(
    id INTEGER PRIMARY KEY,
    stream_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    entity_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applied_seqs(
    stream_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    applied_at TEXT NOT NULL,
    PRIMARY KEY(stream_id, seq)
);
CREATE TABLE IF NOT EXISTS harvest_tasks(
    id INTEGER PRIMARY KEY,
    source_dir TEXT NOT NULL,
    stream_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    event_count INTEGER NOT NULL DEFAULT 0,
    apply_run_id INTEGER,
    report_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS harvest_shards(
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    event_count INTEGER NOT NULL DEFAULT 0,
    first_seq INTEGER,
    last_seq INTEGER,
    status TEXT NOT NULL,
    reason TEXT,
    duplicate_of INTEGER,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_harvest_shards_task ON harvest_shards(task_id, id);
CREATE INDEX IF NOT EXISTS idx_harvest_shards_sha ON harvest_shards(sha256);
CREATE INDEX IF NOT EXISTS idx_harvest_shards_status ON harvest_shards(status);
CREATE INDEX IF NOT EXISTS idx_ledger_run ON change_ledger(run_id);
"""


def _ensure_column(conn, table: str, column: str, declaration: str) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def init_db():
    conn = connect()
    try:
        conn.executescript(SCHEMA)

        # 兼容旧库：apply_runs / change_ledger 需要记录来源采集任务（同源对账）。
        _ensure_column(conn, "apply_runs", "harvest_task_id", "INTEGER")
        _ensure_column(conn, "change_ledger", "harvest_task_id", "INTEGER")
        _ensure_column(conn, "change_ledger", "harvest_shard_id", "INTEGER")

        if conn.execute("SELECT COUNT(*) c FROM streams").fetchone()["c"] == 0:
            conn.executemany(
                """
                INSERT INTO streams(name, fixture_path, entity_type, apply_cursor, enabled, note)
                VALUES (?,?,?,?,?,?)
                """,
                [
                    (
                        "Orders CDC",
                        "orders_cdc.jsonl",
                        "order",
                        0,
                        1,
                        "clean：seq 1→5 连续；含一次 delete",
                    ),
                    (
                        "Inventory CDC",
                        "inventory_cdc.jsonl",
                        "inventory",
                        0,
                        1,
                        "clean：seq 1→3 连续库存变更",
                    ),
                ],
            )
            conn.execute("INSERT INTO settings(key, value) VALUES ('project_label', 'Changeflow')")
            conn.execute(
                "INSERT INTO settings(key, value) VALUES ('gap_policy', 'stop_quarantine')"
            )
            conn.commit()

        # 采集配置：目录可改；同名同内容分片默认跳过。
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES ('harvest_source_dir', 'harvest_demo')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES ('harvest_dupe_policy', 'skip_duplicate_shard')"
        )

        # 采集专用流：不直接绑定夹具文件，由「采集巡检」把目录分片入账后应用。
        if conn.execute("SELECT 1 FROM streams WHERE entity_type='harvest'").fetchone() is None:
            conn.execute(
                """
                INSERT INTO streams(name, fixture_path, entity_type, apply_cursor, enabled, note)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    "Harvest CDC（采集演示）",
                    "",
                    "harvest",
                    0,
                    1,
                    "采集专用流：由采集任务入账，不直接 Apply 夹具",
                ),
            )
        conn.commit()
    finally:
        conn.close()
