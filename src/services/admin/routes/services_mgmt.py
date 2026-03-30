"""Service management routes: view/restart services via admin panel."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request

from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_session_store, require_admin

router = APIRouter(prefix="/api/admin/services", tags=["admin-services"])


@router.get("")
async def list_services(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> list[dict[str, Any]]:
    """Aggregate service status from all node heartbeats."""
    store = get_session_store(request)
    keys = store.client.keys("rdp:node:*")
    services: list[dict[str, Any]] = []
    for k in keys:
        raw = store.client.get(k)
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
