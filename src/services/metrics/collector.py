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
from redis_store import keys

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
        self._prev_net: tuple[int, int] | None = None
        self._prev_ts: float = 0.0
        freq = psutil.cpu_freq()
        self._cpu_name = self._detect_cpu_name()
        self._cpu_freq_mhz = int(freq.current) if freq else 0

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

    @staticmethod
    def _read_host_net() -> tuple[int, int]:
        """Read host network bytes via /host/proc/1/net/dev (PID 1 = host network ns)."""
        HOST_NET_DEV = "/host/proc/1/net/dev"
        try:
            total_recv, total_sent = 0, 0
            with open(HOST_NET_DEV) as f:
                for line in f:
                    parts = line.split()
                    if len(parts) < 10 or not parts[0].endswith(":"):
                        continue
                    iface = parts[0].rstrip(":")
                    if iface == "lo":
                        continue
                    total_recv += int(parts[1])
                    total_sent += int(parts[9])
            return total_recv, total_sent
        except Exception:
            net = psutil.net_io_counters()
            return net.bytes_recv, net.bytes_sent

    def _snapshot(self) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        disk = psutil.disk_usage("/")
        load1, load5, load15 = psutil.getloadavg()

        host_recv, host_sent = self._read_host_net()
        now_ts = time.time()
        net_sent_sec = 0.0
        net_recv_sec = 0.0
        if self._prev_net is not None and (now_ts - self._prev_ts) > 0:
            dt = now_ts - self._prev_ts
            net_sent_sec = (host_sent - self._prev_net[0]) / dt
            net_recv_sec = (host_recv - self._prev_net[1]) / dt
        self._prev_net = (host_sent, host_recv)
        self._prev_ts = now_ts

        return {
            "ts": int(now_ts),
            "instance_id": self._instance_id,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "cpu_count": psutil.cpu_count() or 1,
            "cpu_name": self._cpu_name,
            "cpu_freq_mhz": self._cpu_freq_mhz,
            "cpu_load_1": round(load1, 2),
            "cpu_load_5": round(load5, 2),
            "cpu_load_15": round(load15, 2),
            "mem_total": int(vm.total),
            "mem_used": int(vm.used),
            "mem_percent": vm.percent,
            "swap_total": int(sw.total),
            "swap_used": int(sw.used),
            "swap_percent": sw.percent,
            "disk_total": int(disk.total),
            "disk_used": int(disk.used),
            "disk_percent": disk.percent,
            "net_bytes_sent_sec": round(net_sent_sec),
            "net_bytes_recv_sec": round(net_recv_sec),
            "active_sessions": self._count_active_sessions(),
        }

    def _publish_redis(self, snap: dict[str, Any]) -> None:
        raw = json.dumps(snap, ensure_ascii=False)
        iid = self._instance_id
        pipe = self._redis.pipeline(transaction=False)
        pipe.setex(keys.METRICS_LATEST.format(instance_id=iid), keys.METRICS_LATEST_TTL, raw)
        pipe.lpush(keys.METRICS_SERIES.format(instance_id=iid), raw)
        pipe.ltrim(keys.METRICS_SERIES.format(instance_id=iid), 0, SERIES_MAX_LEN)
        pipe.setex(keys.HEARTBEAT.format(instance_id=iid), HEARTBEAT_REDIS_TTL, raw)
        pipe.execute()

    async def _heartbeat_pg(self, snap: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        hostname = socket.gethostname()
        resources = {k: v for k, v in snap.items() if k not in ("ts", "instance_id")}
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

    def _count_active_sessions(self) -> int:
        try:
            return sum(1 for _ in self._redis.scan_iter(match=keys.ACTIVE_SCAN, count=200))
        except Exception:
            return 0

    @staticmethod
    def _detect_cpu_name() -> str:
        name = platform.processor()
        if name:
            return name
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return platform.machine() or "Unknown"

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
