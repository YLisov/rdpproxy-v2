from __future__ import annotations

import json
import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.history import ConnectionEvent, ConnectionHistory
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_config, get_db_sessionmaker, get_session_store, require_admin

router = APIRouter(prefix="/api/admin/sessions", tags=["admin-sessions"])


class ActiveSessionOut(BaseModel):
    connection_id: str
    instance_id: str
    username: str | None = None
    server_display: str | None = None
    server_address: str | None = None
    server_port: int | None = None
    client_ip: str | None = None
    started_at: str | None = None
    connection_quality: str | None = None


async def _db(request: Request) -> AsyncSession:
    return get_db_sessionmaker(request)()


def _redis(request: Request):
    return get_session_store(request).client


@router.get("/active")
async def active_sessions(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> list[ActiveSessionOut]:
    redis = _redis(request)
    keys = redis.keys("rdp:active:*")
    out: list[ActiveSessionOut] = []
    for k in keys:
        # format: rdp:active:{instance_id}:{connection_id}
        parts = str(k).split(":")
        if len(parts) < 4:
            continue
        instance_id = parts[2]
        connection_id = parts[3]
        raw = redis.get(k)
        data: dict[str, Any] = {}
        if raw and str(raw) != "1":
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
        out.append(
            ActiveSessionOut(
                instance_id=data.get("instance_id") or instance_id,
                connection_id=connection_id,
                username=data.get("username"),
                server_display=data.get("server_display"),
                server_address=data.get("server_address"),
                server_port=int(data["server_port"]) if data.get("server_port") is not None else None,
                client_ip=data.get("client_ip"),
                started_at=data.get("started_at"),
                connection_quality=data.get("connection_quality"),
            )
        )
    return out


@router.get("/history")
async def sessions_history(
    request: Request,
    username: list[str] = Query(default=[]),
    server_id: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
    client_ip: list[str] = Query(default=[]),
    from_ts: str | None = Query(default=None, alias="from"),
    to_ts: str | None = Query(default=None, alias="to"),
    page: int = 1,
    per_page: int = 50,
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, Any]:
    session = await _db(request)
    try:
        stmt = sa.select(ConnectionHistory).order_by(ConnectionHistory.started_at.desc())
        if username:
            stmt = stmt.where(ConnectionHistory.username.in_(username))
        if server_id:
            uuids = []
            for v in server_id:
                try:
                    uuids.append(uuid.UUID(v))
                except Exception:
                    continue
            if uuids:
                stmt = stmt.where(ConnectionHistory.server_id.in_(uuids))
        if status:
            stmt = stmt.where(ConnectionHistory.status.in_(status))
        if client_ip:
            stmt = stmt.where(ConnectionHistory.client_ip.in_(client_ip))
        if from_ts:
            stmt = stmt.where(ConnectionHistory.started_at >= from_ts)
        if to_ts:
            stmt = stmt.where(ConnectionHistory.started_at <= to_ts)

        total = await session.scalar(sa.select(sa.func.count()).select_from(stmt.subquery()))
        items = (
            await session.execute(stmt.offset((max(page, 1) - 1) * max(per_page, 1)).limit(max(1, min(per_page, 200))))
        ).scalars().all()
        return {
            "items": [
                {
                    "id": str(i.id),
                    "instance_id": i.instance_id,
                    "username": i.username,
                    "server_id": str(i.server_id) if i.server_id else None,
                    "server_display": i.server_display,
                    "server_address": i.server_address,
                    "server_port": i.server_port,
                    "client_ip": i.client_ip,
                    "started_at": i.started_at.isoformat() if i.started_at else None,
                    "ended_at": i.ended_at.isoformat() if i.ended_at else None,
                    "bytes_to_client": i.bytes_to_client,
                    "bytes_to_backend": i.bytes_to_backend,
                    "disconnect_reason": i.disconnect_reason,
                    "status": i.status,
                }
                for i in items
            ],
            "page": page,
            "per_page": per_page,
            "total": int(total or 0),
        }
    finally:
        await session.close()


@router.get("/history.csv")
async def sessions_history_csv(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> PlainTextResponse:
    session = await _db(request)
    try:
        rows = (
            await session.execute(
                sa.select(ConnectionHistory).order_by(ConnectionHistory.started_at.desc()).limit(5000)
            )
        ).scalars().all()
        cols = [
            "id",
            "instance_id",
            "username",
            "server_display",
            "server_address",
            "server_port",
            "client_ip",
            "started_at",
            "ended_at",
            "bytes_to_client",
            "bytes_to_backend",
            "disconnect_reason",
            "status",
        ]
        lines = [",".join(cols)]
        for r in rows:
            row = [
                str(r.id),
                str(r.instance_id),
                str(r.username),
                str(r.server_display or ""),
                str(r.server_address),
                str(r.server_port),
                str(r.client_ip),
                r.started_at.isoformat() if r.started_at else "",
                r.ended_at.isoformat() if r.ended_at else "",
                str(r.bytes_to_client or 0),
                str(r.bytes_to_backend or 0),
                str(r.disconnect_reason or ""),
                str(r.status),
            ]
            lines.append(",".join(json.dumps(v, ensure_ascii=False) for v in row))
        return PlainTextResponse("\n".join(lines), media_type="text/csv")
    finally:
        await session.close()


@router.get("/{connection_id}")
async def session_detail(request: Request, connection_id: str, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, Any]:
    session = await _db(request)
    try:
        row = await session.execute(sa.select(ConnectionHistory).where(ConnectionHistory.id == uuid.UUID(connection_id)))
        item = row.scalars().first()
        if not item:
            raise HTTPException(status_code=404, detail="Connection not found")
        return {
            "id": str(item.id),
            "instance_id": item.instance_id,
            "username": item.username,
            "server_id": str(item.server_id) if item.server_id else None,
            "server_display": item.server_display,
            "server_address": item.server_address,
            "server_port": item.server_port,
            "client_ip": item.client_ip,
            "started_at": item.started_at.isoformat() if item.started_at else None,
            "ended_at": item.ended_at.isoformat() if item.ended_at else None,
            "bytes_to_client": item.bytes_to_client,
            "bytes_to_backend": item.bytes_to_backend,
            "disconnect_reason": item.disconnect_reason,
            "status": item.status,
        }
    finally:
        await session.close()


@router.get("/{connection_id}/events")
async def session_events(request: Request, connection_id: str, _: AdminWebSessionData = Depends(require_admin)) -> list[dict[str, Any]]:
    session = await _db(request)
    try:
        rows = await session.execute(
            sa.select(ConnectionEvent)
            .where(ConnectionEvent.connection_id == uuid.UUID(connection_id))
            .order_by(ConnectionEvent.ts.asc())
        )
        return [
            {
                "id": int(e.id),
                "ts": e.ts.isoformat() if e.ts else None,
                "event_type": e.event_type,
                "detail": e.detail or {},
            }
            for e in rows.scalars().all()
        ]
    finally:
        await session.close()


@router.post("/{connection_id}/kill")
async def kill_session(request: Request, connection_id: str, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, str]:
    redis = _redis(request)
    instance_id = str(get_config(request).instance.id)
    redis.setex(f"rdp:kill:{connection_id}", 60, "1")
    redis.delete(f"rdp:active:{instance_id}:{connection_id}")

    session = await _db(request)
    try:
        await session.execute(
            sa.update(ConnectionHistory)
            .where(ConnectionHistory.id == uuid.UUID(connection_id), ConnectionHistory.status == "active")
            .values(status="killed", disconnect_reason="admin_kill")
        )
        await session.commit()
    finally:
        await session.close()
    return {"status": "ok"}
