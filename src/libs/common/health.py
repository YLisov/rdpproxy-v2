"""Health check utilities for FastAPI services and HAProxy probes."""

from __future__ import annotations

from typing import Any

import redis as redis_lib
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import text


async def check_health(
    *, db_sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    redis_client: redis_lib.Redis | None = None,
) -> dict[str, Any]:
    """Return health status dict with db/redis sub-checks."""
    result: dict[str, Any] = {"status": "ok"}
    errors: list[str] = []

    if db_sessionmaker is not None:
        try:
            async with db_sessionmaker() as session:
                await session.execute(text("SELECT 1"))
            result["db"] = "ok"
        except Exception as exc:
            result["db"] = "error"
            errors.append(f"db: {exc}")

    if redis_client is not None:
        try:
            redis_client.ping()
            result["redis"] = "ok"
        except Exception as exc:
            result["redis"] = "error"
            errors.append(f"redis: {exc}")

    if errors:
        result["status"] = "degraded"
        result["errors"] = errors
    return result
