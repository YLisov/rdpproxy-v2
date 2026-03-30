"""Cluster management routes: node status, heartbeats."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request

from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_session_store, require_admin

router = APIRouter(prefix="/api/admin/cluster", tags=["admin-cluster"])


@router.get("/nodes")
async def list_nodes(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> list[dict[str, Any]]:
    """List all cluster nodes from Redis heartbeats."""
    store = get_session_store(request)
    keys = store.client.keys("rdp:node:*")
    nodes: list[dict[str, Any]] = []
    for k in keys:
        raw = store.client.get(k)
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
    store = get_session_store(request)
    raw = store.client.get(f"rdp:node:{instance_id}")
    if not raw:
        return {"error": "Node not found"}
    return json.loads(raw)
