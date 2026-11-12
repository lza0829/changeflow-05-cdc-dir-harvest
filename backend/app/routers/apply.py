from fastapi import APIRouter, HTTPException

from app.db import connect
from app.repositories import runs as runs_repo
from app.schemas.entities import ApplyRequest
from app.services import apply_service

router = APIRouter(tags=["apply"])


@router.get("/runs")
def list_runs():
    conn = connect()
    try:
        return runs_repo.list_runs(conn)
    finally:
        conn.close()


@router.get("/runs/{run_id}")
def get_run(run_id: int):
    conn = connect()
    try:
        run = runs_repo.get_run(conn, run_id)
        if not run:
            raise HTTPException(404, "run not found")
        return run
    finally:
        conn.close()


@router.post("/apply")
def apply(body: ApplyRequest):
    try:
        return apply_service.run_apply(body.stream_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
