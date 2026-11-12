from fastapi import APIRouter

from app.db import connect
from app.repositories import cursors as cursor_repo

router = APIRouter(tags=["cursors"])


@router.get("/cursors")
def list_cursors():
    conn = connect()
    try:
        return cursor_repo.list_cursor_view(conn)
    finally:
        conn.close()
