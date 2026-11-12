from fastapi import APIRouter

from app.db import connect
from app.repositories import quarantine as quarantine_repo

router = APIRouter(tags=["quarantine"])


@router.get("/quarantine")
def list_quarantine():
    conn = connect()
    try:
        return quarantine_repo.list_quarantine(conn)
    finally:
        conn.close()
