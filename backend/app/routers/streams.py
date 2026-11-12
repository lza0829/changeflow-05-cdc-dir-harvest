from fastapi import APIRouter, HTTPException

from app.db import connect
from app.repositories import streams as streams_repo
from app.schemas.entities import StreamPatch
from app.services import apply_service

router = APIRouter(tags=["streams"])


@router.get("/streams")
def list_streams():
    conn = connect()
    try:
        return streams_repo.list_streams(conn)
    finally:
        conn.close()


@router.get("/streams/{stream_id}")
def get_stream(stream_id: int):
    conn = connect()
    try:
        stream = streams_repo.get_stream(conn, stream_id)
        if not stream:
            raise HTTPException(404, "stream not found")
        return stream
    finally:
        conn.close()


@router.patch("/streams/{stream_id}")
def patch_stream(stream_id: int, body: StreamPatch):
    conn = connect()
    try:
        stream = streams_repo.get_stream(conn, stream_id)
        if not stream:
            raise HTTPException(404, "stream not found")
        if body.enabled is not None:
            streams_repo.set_enabled(conn, stream_id, body.enabled)
        conn.commit()
        return streams_repo.get_stream(conn, stream_id)
    finally:
        conn.close()


@router.get("/streams/{stream_id}/preview")
def preview(stream_id: int):
    try:
        return apply_service.preview_stream(stream_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
