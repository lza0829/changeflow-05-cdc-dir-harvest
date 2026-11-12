from fastapi import APIRouter

from app.db import connect
from app.repositories import sink as sink_repo

router = APIRouter(tags=["sink"])


@router.get("/sink")
def list_sink():
    conn = connect()
    try:
        return sink_repo.list_sink(conn)
    finally:
        conn.close()
