"""Portal health check endpoint for HAProxy probes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from common.health import check_health

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    db_factory = getattr(request.app.state, "db_sessionmaker", None)
    redis_client = getattr(request.app.state, "redis_client", None)
    return await check_health(db_sessionmaker=db_factory, redis_client=redis_client)
