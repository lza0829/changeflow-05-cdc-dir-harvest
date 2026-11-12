from fastapi import APIRouter

from app.db import connect
from app.repositories import ledger as ledger_repo

router = APIRouter(tags=["ledger"])


@router.get("/ledger")
def list_ledger():
    conn = connect()
    try:
        return ledger_repo.list_ledger(conn)
    finally:
        conn.close()
