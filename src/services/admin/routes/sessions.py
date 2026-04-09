from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from db.models.history import ConnectionEvent, ConnectionHistory
from redis_store import keys
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import (
    get_config,
    get_db_session,
    get_db_sessionmaker,
    get_redis_client,
    require_admin,
)

router = APIRouter(prefix="/api/admin/sessions", tags=["admin-sessions"])


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid datetime: {value}") from None


class QualityDetail(BaseModel):
    rtt_ms: float | None = None
    rtt_var_ms: float | None = None
    jitter_ms: float | None = None
    retransmits: int | None = None
    total_retrans: int | None = None
    lost: int | None = None
    cwnd: int | None = None
    rating: str | None = None


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
    quality_detail: QualityDetail | None = None


@router.get("/active")
async def active_sessions(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> list[ActiveSessionOut]:
    rc = get_redis_client(request)
    active_keys = list(rc.scan_iter(match=keys.ACTIVE_SCAN, count=200))
    out: list[ActiveSessionOut] = []
    for k in active_keys:
        parts = str(k).split(":")
        if len(parts) < 4:
            continue
        instance_id = parts[2]
        connection_id = parts[3]
        raw = rc.get(k)
        data: dict[str, Any] = {}
        if raw and str(raw) != "1":
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
        qd_raw = data.get("quality_detail")
        qd = QualityDetail(**qd_raw) if isinstance(qd_raw, dict) else None
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
                quality_detail=qd,
            )
        )
    return out


@router.get("/history")
async def sessions_history(
    request: Request,
    username: list[str] = Query(default=[]),
    server_id: list[str] = Query(default=[]),
    server_display: str | None = Query(default=None),
    server_address: str | None = Query(default=None),
    status: list[str] = Query(default=[]),
    client_ip: list[str] = Query(default=[]),
    disconnect_reason: str | None = Query(default=None),
    from_ts: str | None = Query(default=None, alias="from"),
    to_ts: str | None = Query(default=None, alias="to"),
    ended_from: str | None = Query(default=None),
    ended_to: str | None = Query(default=None),
    exclude_active: bool = Query(default=True),
    page: int = Query(default=1, ge=1, le=10000),
    per_page: int = Query(default=50, ge=1, le=200),
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, Any]:
    session = await get_db_session(request)
    try:
        stmt = sa.select(ConnectionHistory).order_by(ConnectionHistory.started_at.desc())
        if exclude_active:
            stmt = stmt.where(ConnectionHistory.status != "active")
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
        if server_display:
            stmt = stmt.where(ConnectionHistory.server_display.ilike(f"%{server_display}%"))
        if server_address:
            stmt = stmt.where(ConnectionHistory.server_address.ilike(f"%{server_address}%"))
        if status:
            stmt = stmt.where(ConnectionHistory.status.in_(status))
        if client_ip:
            stmt = stmt.where(ConnectionHistory.client_ip.in_(client_ip))
        if disconnect_reason:
            stmt = stmt.where(ConnectionHistory.disconnect_reason.ilike(f"%{disconnect_reason}%"))
        if from_ts:
            stmt = stmt.where(ConnectionHistory.started_at >= _parse_dt(from_ts))
        if to_ts:
            stmt = stmt.where(ConnectionHistory.started_at <= _parse_dt(to_ts))
        if ended_from:
            stmt = stmt.where(ConnectionHistory.ended_at >= _parse_dt(ended_from))
        if ended_to:
            stmt = stmt.where(ConnectionHistory.ended_at <= _parse_dt(ended_to))

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


@router.get("/history/reasons")
async def disconnect_reasons(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> list[str]:
    session = await get_db_session(request)
    try:
        rows = await session.execute(
            sa.select(sa.distinct(ConnectionHistory.disconnect_reason))
            .where(ConnectionHistory.disconnect_reason.isnot(None), ConnectionHistory.disconnect_reason != "")
            .order_by(ConnectionHistory.disconnect_reason)
        )
        return [str(r) for r in rows.scalars().all()]
    finally:
        await session.close()


@router.get("/history.csv")
async def sessions_history_csv(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> PlainTextResponse:
    session = await get_db_session(request)
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
    try:
        cid = uuid.UUID(connection_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid connection_id") from None
    session = await get_db_session(request)
    try:
        row = await session.execute(sa.select(ConnectionHistory).where(ConnectionHistory.id == cid))
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
    try:
        cid = uuid.UUID(connection_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid connection_id") from None
    session = await get_db_session(request)
    try:
        rows = await session.execute(
            sa.select(ConnectionEvent)
            .where(ConnectionEvent.connection_id == cid)
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


@router.post("/kill-all")
async def kill_all_sessions(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, Any]:
    rc = get_redis_client(request)
    active_keys = list(rc.scan_iter(match=keys.ACTIVE_SCAN, count=200))
    killed = 0
    session = await get_db_session(request)
    try:
        for k in active_keys:
            parts = str(k).split(":")
            if len(parts) < 4:
                continue
            connection_id = parts[3]
            rc.setex(keys.KILL_SESSION.format(connection_id=connection_id), keys.KILL_TTL, "1")
            rc.delete(k)
            await session.execute(
                sa.update(ConnectionHistory)
                .where(ConnectionHistory.id == uuid.UUID(connection_id), ConnectionHistory.status == "active")
                .values(status="killed", disconnect_reason="admin_kill_all")
            )
            killed += 1
        await session.commit()
    finally:
        await session.close()
    return {"status": "ok", "killed": killed}


@router.post("/{connection_id}/kill")
async def kill_session(request: Request, connection_id: str, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, str]:
    try:
        cid = uuid.UUID(connection_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid connection_id") from None

    rc = get_redis_client(request)
    instance_id = str(get_config(request).instance.id)
    rc.setex(keys.KILL_SESSION.format(connection_id=connection_id), keys.KILL_TTL, "1")
    rc.delete(keys.ACTIVE_SESSION.format(instance_id=instance_id, connection_id=connection_id))

    session = await get_db_session(request)
    try:
        await session.execute(
            sa.update(ConnectionHistory)
            .where(ConnectionHistory.id == cid, ConnectionHistory.status == "active")
            .values(status="killed", disconnect_reason="admin_kill")
        )
        await session.commit()
    finally:
        await session.close()
    return {"status": "ok"}
