from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.history import ConnectionHistory
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_db_sessionmaker, get_session_store, require_admin

router = APIRouter(prefix="/api/admin/stats", tags=["admin-stats"])


async def _db(request: Request) -> AsyncSession:
    return get_db_sessionmaker(request)()


def _redis(request: Request):
    return get_session_store(request).client


@router.get("/overview")
async def overview(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, Any]:
    session = await _db(request)
    try:
        active = await session.scalar(
            sa.select(sa.func.count(ConnectionHistory.id)).where(ConnectionHistory.status == "active")
        )
        total = await session.scalar(sa.select(sa.func.count(ConnectionHistory.id)))
        return {"active_sessions": int(active or 0), "total_sessions": int(total or 0)}
    finally:
        await session.close()


@router.get("/resources")
async def resources(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, Any]:
    redis = _redis(request)
    raw = redis.get("rdp:metrics:latest")
    latest = {}
    if raw:
        try:
            latest = json.loads(raw)
        except Exception:
            latest = {}
    points_raw = redis.lrange("rdp:metrics:series", 0, 300)
    points = []
    for p in points_raw:
        try:
            points.append(json.loads(p))
        except Exception:
            pass
    return {"latest": latest, "points": points}
