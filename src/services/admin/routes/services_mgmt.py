"""Service management routes: view/restart services via admin panel."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from redis_store import keys
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_redis_client, require_admin

router = APIRouter(prefix="/api/admin/services", tags=["admin-services"])
logger = logging.getLogger("rdpproxy.admin.services")


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
