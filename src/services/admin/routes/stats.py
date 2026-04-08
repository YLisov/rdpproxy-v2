from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.history import ConnectionHistory
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_config, get_db_sessionmaker, get_session_store, require_admin

router = APIRouter(prefix="/api/admin/stats", tags=["admin-stats"])

_PERIOD_POINTS = {"1h": 360, "6h": 2160, "24h": 8640}


async def _db(request: Request) -> AsyncSession:
    return get_db_sessionmaker(request)()


def _redis(request: Request):
    return get_session_store(request).client


def _instance_id(request: Request) -> str:
    return get_config(request).instance.id


@router.get("/overview")
async def overview(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, Any]:
    redis = _redis(request)
    keys = redis.keys("rdp:active:*")
    today_start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
    async with get_db_sessionmaker(request)() as db:
        row = await db.execute(
            sa.select(sa.func.count()).select_from(ConnectionHistory).where(
                ConnectionHistory.started_at >= today_start
            )
        )
        today_count = row.scalar() or 0
    return {"active_sessions": len(keys), "today_connections": today_count}


@router.get("/resources")
async def resources(
    request: Request,
    period: str = Query("1h"),
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, Any]:
    redis = _redis(request)
    iid = _instance_id(request)
    raw = redis.get(f"rdp:metrics:{iid}:latest")
    latest = {}
    if raw:
        try:
            latest = json.loads(raw)
        except Exception:
            latest = {}
    n = _PERIOD_POINTS.get(period, 360)
    points_raw = redis.lrange(f"rdp:metrics:{iid}:series", 0, n)
    points = []
    for p in points_raw:
        try:
            points.append(json.loads(p))
        except Exception:
            pass
    return {"latest": latest, "points": points}
