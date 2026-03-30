"""System metrics collector: gathers CPU/RAM/disk/connections data
and publishes to Redis (real-time) + PostgreSQL (cluster_nodes heartbeat)."""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import socket
import time
from datetime import datetime, timezone
from typing import Any

import psutil
import redis as redis_lib
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models.node import ClusterNode

logger = logging.getLogger("rdpproxy.metrics")

SERIES_MAX_LEN = 24 * 60 * 6  # ~24h at 10s interval
HEARTBEAT_REDIS_TTL = 60


class MetricsCollector:
    def __init__(
        self,
        *,
        redis_client: redis_lib.Redis,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        instance_id: str,
        lan_ip: str,
        interval_sec: int = 10,
    ) -> None:
        self._redis = redis_client
        self._db_factory = db_sessionmaker
        self._instance_id = instance_id
        self._lan_ip = lan_ip
        self._interval = max(5, interval_sec)
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="metrics_collector")
        logger.info("Metrics collector started (interval=%ds)", self._interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.wait([self._task], timeout=3.0)

    def _snapshot(self) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "ts": int(time.time()),
            "instance_id": self._instance_id,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "cpu_count": psutil.cpu_count() or 1,
            "mem_total": int(vm.total),
            "mem_used": int(vm.used),
            "mem_percent": vm.percent,
            "disk_total": int(disk.total),
            "disk_used": int(disk.used),
            "disk_percent": disk.percent,
        }

    def _publish_redis(self, snap: dict[str, Any]) -> None:
        raw = json.dumps(snap, ensure_ascii=False)
        pipe = self._redis.pipeline(transaction=False)
        pipe.setex(f"rdp:metrics:{self._instance_id}:latest", 120, raw)
        pipe.lpush(f"rdp:metrics:{self._instance_id}:series", raw)
        pipe.ltrim(f"rdp:metrics:{self._instance_id}:series", 0, SERIES_MAX_LEN)
        pipe.setex(f"rdp:heartbeat:{self._instance_id}", HEARTBEAT_REDIS_TTL, raw)
        pipe.execute()

    async def _heartbeat_pg(self, snap: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        hostname = socket.gethostname()
        resources = {
            "cpu_percent": snap["cpu_percent"],
            "cpu_count": snap["cpu_count"],
            "mem_total": snap["mem_total"],
            "mem_used": snap["mem_used"],
            "mem_percent": snap["mem_percent"],
            "disk_total": snap["disk_total"],
            "disk_used": snap["disk_used"],
            "disk_percent": snap["disk_percent"],
        }
        services = self._detect_services()
        async with self._db_factory() as session:
            stmt = pg_insert(ClusterNode).values(
                instance_id=self._instance_id,
                hostname=hostname,
                ip=self._lan_ip,
                services=services,
                resources=resources,
                last_heartbeat=now,
                registered_at=now,
            ).on_conflict_do_update(
                index_elements=[ClusterNode.instance_id],
                set_={
                    "hostname": hostname,
                    "ip": self._lan_ip,
                    "services": services,
                    "resources": resources,
                    "last_heartbeat": now,
                },
            )
            await session.execute(stmt)
            await session.commit()

    @staticmethod
    def _detect_services() -> dict[str, str]:
        """Report which services are co-located (in Docker each container runs one)."""
        return {"metrics": "running"}

    async def _loop(self) -> None:
        psutil.cpu_percent(interval=None)
        while not self._stop.is_set():
            try:
                snap = self._snapshot()
                self._publish_redis(snap)
                await self._heartbeat_pg(snap)
            except Exception:
                logger.exception("Metrics collection tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
