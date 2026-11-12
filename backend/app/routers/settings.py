from fastapi import APIRouter, HTTPException

from app.db import connect
from app.repositories import settings as settings_repo
from app.schemas.entities import SettingPut

router = APIRouter(tags=["settings"])


@router.get("/settings")
def list_settings():
    conn = connect()
    try:
        return settings_repo.as_list(conn)
    finally:
        conn.close()


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingPut):
    conn = connect()
    try:
        settings_repo.put(conn, key, body.value)
        conn.commit()
        return {"key": key, "value": body.value}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    finally:
        conn.close()
