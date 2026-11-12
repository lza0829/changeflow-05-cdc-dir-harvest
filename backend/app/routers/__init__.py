from fastapi import APIRouter

from app.routers import apply, cursors, dashboard, ledger, quarantine, settings, sink, streams

api = APIRouter(prefix="/api")
api.include_router(dashboard.router)
api.include_router(streams.router)
api.include_router(apply.router)
api.include_router(ledger.router)
api.include_router(quarantine.router)
api.include_router(sink.router)
api.include_router(cursors.router)
api.include_router(settings.router)
