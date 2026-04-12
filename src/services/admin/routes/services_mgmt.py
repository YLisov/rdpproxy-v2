"""Service management routes: view/restart services via admin panel."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Request

from redis_store import keys
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_redis_client, require_admin

router = APIRouter(prefix="/api/admin/services", tags=["admin-services"])
logger = logging.getLogger("rdpproxy.admin.services")

_SERVICE_CHECKS: list[dict[str, Any]] = [
    {"name": "postgres", "type": "tcp", "host": "postgres", "port": 5432},
    {"name": "redis", "type": "tcp", "host": "redis", "port": 6379},
    {"name": "admin", "type": "self"},
    {"name": "portal", "type": "http", "host": "portal", "port": 8001, "path": "/health"},
    {"name": "rdp-relay", "type": "tcp", "host": "rdp-relay", "port": 8002},
    {"name": "haproxy", "type": "haproxy_stats", "socket": "/var/run/haproxy/admin.sock"},
    {"name": "metrics", "type": "redis_heartbeat"},
]


async def _check_tcp(host: str, port: int, timeout: float = 2.0) -> tuple[str, float]:
    t0 = time.monotonic()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return "running", round((time.monotonic() - t0) * 1000, 1)
    except Exception:
        return "stopped", 0


async def _check_http(host: str, port: int, path: str, timeout: float = 2.0) -> tuple[str, float]:
    t0 = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        request = f"GET {path} HTTP/1.0\r\nHost: {host}\r\n\r\n".encode()
        writer.write(request)
        await writer.drain()
        response = await asyncio.wait_for(reader.read(1024), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        status_line = response.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 200 " in status_line:
            return "running", round((time.monotonic() - t0) * 1000, 1)
        return "unhealthy", round((time.monotonic() - t0) * 1000, 1)
    except Exception:
        return "stopped", 0


async def _check_haproxy_stats(socket_path: str, timeout: float = 2.0) -> tuple[str, float]:
    t0 = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(socket_path), timeout=timeout,
        )
        writer.write(b"show info\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.read(512), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        if b"Uptime" in data:
            return "running", round((time.monotonic() - t0) * 1000, 1)
        return "unhealthy", round((time.monotonic() - t0) * 1000, 1)
    except Exception:
        return "stopped", 0


def _check_redis_heartbeat(request_or_rc: Any) -> tuple[str, float]:
    """Check if metrics collector recently wrote a heartbeat to Redis."""
    rc = request_or_rc
    try:
        for k in rc.scan_iter(match="rdp:heartbeat:*", count=10):
            ttl = rc.ttl(k)
            if ttl > 0:
                return "running", 0
        return "stopped", 0
    except Exception:
        return "stopped", 0


async def _check_one(spec: dict[str, Any], redis_client: Any = None) -> dict[str, Any]:
    stype = spec["type"]
    if stype == "self":
        return {"name": spec["name"], "status": "running", "latency_ms": 0}
    if stype == "redis_heartbeat":
        status, latency = _check_redis_heartbeat(redis_client)
        return {"name": spec["name"], "status": status, "latency_ms": latency}
    if stype == "haproxy_stats":
        status, latency = await _check_haproxy_stats(spec.get("socket", "/var/run/haproxy/admin.sock"))
    elif stype == "http":
        status, latency = await _check_http(spec["host"], spec["port"], spec.get("path", "/"))
    else:
        status, latency = await _check_tcp(spec["host"], spec["port"])
    return {"name": spec["name"], "status": status, "latency_ms": latency}


@router.get("/health")
async def service_health(
    request: Request,
    _: AdminWebSessionData = Depends(require_admin),
) -> list[dict[str, Any]]:
    """Check reachability of all services via TCP/HTTP probes."""
    rc = get_redis_client(request)
    results = await asyncio.gather(*[_check_one(s, redis_client=rc) for s in _SERVICE_CHECKS])
    return list(results)


@router.get("")
async def list_services(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> list[dict[str, Any]]:
    """Aggregate service status from all node heartbeats."""
    rc = get_redis_client(request)
    node_keys = list(rc.scan_iter(match=keys.NODE_SCAN, count=100))
    services: list[dict[str, Any]] = []
    for k in node_keys:
        raw = rc.get(k)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        node_id = data.get("hostname", str(k))
        for svc_name, svc_info in (data.get("services") or {}).items():
            services.append({
                "node": node_id,
                "instance_id": data.get("hostname"),
                "service": svc_name,
                "status": svc_info.get("status", "unknown"),
                "port": svc_info.get("port"),
                "pid": svc_info.get("pid"),
            })
    return services


@router.post("/restart")
async def restart_service(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, str]:
    """Signal all proxy instances to restart via Redis pub/sub."""
    rc = get_redis_client(request)
    rc.set(keys.SIGNAL_RESTART, "1", ex=keys.SIGNAL_RESTART_TTL)
    logger.warning("Admin requested service restart")
    return {"status": "restart_signaled"}
