"""Cluster management routes: node status, heartbeats."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request

from redis_store import keys
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_redis_client, require_admin

router = APIRouter(prefix="/api/admin/cluster", tags=["admin-cluster"])


@router.get("/nodes")
async def list_nodes(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> list[dict[str, Any]]:
    """List all cluster nodes from Redis heartbeats."""
    rc = get_redis_client(request)
    node_keys = list(rc.scan_iter(match=keys.NODE_SCAN, count=100))
    nodes: list[dict[str, Any]] = []
    for k in node_keys:
        raw = rc.get(k)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            nodes.append(data)
        except Exception:
            continue
    return nodes


@router.get("/nodes/{instance_id}")
async def get_node(request: Request, instance_id: str, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, Any]:
    rc = get_redis_client(request)
    raw = rc.get(keys.NODE.format(instance_id=instance_id))
    if not raw:
        return {"error": "Node not found"}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid data"}
