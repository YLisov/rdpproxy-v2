from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.history import ConnectionHistory
from redis_store import keys
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_config, get_db_sessionmaker, get_redis_client, require_admin

router = APIRouter(prefix="/api/admin/stats", tags=["admin-stats"])

_PERIOD_POINTS = {"1h": 360, "6h": 2160, "24h": 8640}


@router.get("/overview")
async def overview(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, Any]:
    rc = get_redis_client(request)
    active_keys = list(rc.scan_iter(match=keys.ACTIVE_SCAN, count=200))
    today_start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
    async with get_db_sessionmaker(request)() as db:
        row = await db.execute(
            sa.select(sa.func.count()).select_from(ConnectionHistory).where(
                ConnectionHistory.started_at >= today_start
            )
        )
        today_count = row.scalar() or 0
    return {"active_sessions": len(active_keys), "today_connections": today_count}


@router.get("/resources")
async def resources(
    request: Request,
    period: str = Query("1h"),
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, Any]:
    rc = get_redis_client(request)
    iid = get_config(request).instance.id
    raw = rc.get(keys.METRICS_LATEST.format(instance_id=iid))
    latest: dict[str, Any] = {}
    if raw:
        try:
            latest = json.loads(raw)
        except Exception:
            latest = {}
    n = _PERIOD_POINTS.get(period, 360)
    points_raw = rc.lrange(keys.METRICS_SERIES.format(instance_id=iid), 0, n)
    points = []
    for p in points_raw:
        try:
            points.append(json.loads(p))
        except Exception:
            pass
    return {"latest": latest, "points": points}
