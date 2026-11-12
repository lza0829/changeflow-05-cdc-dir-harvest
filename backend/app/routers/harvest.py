from fastapi import APIRouter, HTTPException

from app.config import FIXTURES_DIR, HARVEST_ALLOWED_ROOTS, HARVEST_DEMO_DIR
from app.db import connect
from app.repositories import harvest as harvest_repo
from app.repositories import settings as settings_repo
from app.schemas.entities import HarvestRequest
from app.services import apply_service, harvest_service

router = APIRouter(tags=["harvest"])

@router.get("/harvest/config")
def harvest_config():
    conn = connect()
    try:
        demos = sorted(
            p.name
            for p in FIXTURES_DIR.iterdir()
            if p.is_dir() and any(f.suffix == ".jsonl" for f in p.iterdir() if f.is_file())
        )
        return {
            "source_dir": settings_repo.get(conn, "harvest_source_dir", HARVEST_DEMO_DIR),
            "dupe_policy": settings_repo.get(
                conn, "harvest_dupe_policy", "skip_duplicate_shard"
            ),
            "default_stream_id": _harvest_stream_id(conn),
            "allowed_roots": [str(p) for p in HARVEST_ALLOWED_ROOTS],
            "demo_dir": str(FIXTURES_DIR / HARVEST_DEMO_DIR),
            "demo_dirs": demos,
            "suffixes": [".jsonl"],
        }
    finally:
        conn.close()


@router.get("/harvest/tasks")
def list_tasks():
    conn = connect()
    try:
        return harvest_repo.list_tasks(conn)
    finally:
        conn.close()


@router.get("/harvest/tasks/{task_id}")
def get_task(task_id: int):
    try:
        return harvest_service.harvest_detail(task_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/harvest/tasks")
def create_task(body: HarvestRequest):
    # 目录在服务层校验通过后才持久化，避免把非法目录写进配置。
    try:
        return harvest_service.run_harvest(
            source_dir=body.source_dir,
            stream_id=body.stream_id,
            auto_apply=body.auto_apply,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/harvest/tasks/{task_id}/apply")
def apply_task(task_id: int):
    conn = connect()
    try:
        task = harvest_repo.get_task(conn, task_id)
        if not task:
            raise HTTPException(404, "harvest task not found")
        stream_id = int(task["stream_id"])
    finally:
        conn.close()
    try:
        run = apply_service.run_apply_from_harvest(
            stream_id=stream_id, harvest_task_id=task_id
        )
        conn = connect()
        try:
            if run.get("id") is not None:
                harvest_repo.set_apply_run(conn, task_id, int(run["id"]))
                conn.commit()
            return harvest_service.harvest_task_detail(conn, task_id)
        finally:
            conn.close()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _harvest_stream_id(conn) -> int | None:
    row = conn.execute(
        "SELECT id FROM streams WHERE entity_type='harvest' ORDER BY id LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None
