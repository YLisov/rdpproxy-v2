from __future__ import annotations

import re
import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models.server import RdpServer, ServerGroupBinding
from db.models.settings import AdGroupCache
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_db_session, require_admin

router = APIRouter(prefix="/api/admin/servers", tags=["admin-servers"])

_ADDR_PORT_RE = re.compile(r"^(?P<host>[^:]+):(?P<port>\d{1,5})$")


def _split_address(address: str, port: int | None) -> tuple[str, int]:
    raw = (address or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="address is required")

    m = _ADDR_PORT_RE.match(raw)
    if m:
        host = m.group("host").strip()
        p = int(m.group("port"))
        if p < 1 or p > 65535:
            raise HTTPException(status_code=400, detail="Invalid port in address")
        return host, p

    if port is None:
        return raw, 3389
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Invalid port")
    return raw, int(port)


def _parse_group_guids(values: list[str] | None) -> list[uuid.UUID]:
    if not values:
        return []
    out: list[uuid.UUID] = []
    for v in values:
        s = str(v).strip()
        if not s:
            continue
        try:
            out.append(uuid.UUID(s))
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail=f"Invalid group GUID: {s}") from None
    return out


def _handle_integrity_error(exc: IntegrityError) -> None:
    msg = str(exc).lower()
    if "rdp_servers_tech_name_key" in msg or "duplicate key value" in msg:
        raise HTTPException(status_code=409, detail="Сервер с таким technical name уже существует") from None
    raise HTTPException(status_code=400, detail="Нарушение ограничений данных") from None


class ServerOut(BaseModel):
    id: str
    tech_name: str
    display_name: str
    address: str
    port: int
    is_enabled: bool
    sort_order: int
    groups: list[str] = Field(default_factory=list)
    group_details: list[dict[str, str]] = Field(default_factory=list)


class ServerCreate(BaseModel):
    tech_name: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    is_enabled: bool = True
    sort_order: int = 0
    groups: list[str] = Field(default_factory=list)


class ServerUpdate(BaseModel):
    tech_name: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    is_enabled: bool | None = None
    sort_order: int | None = None
    groups: list[str] | None = None


class VisibilityPatch(BaseModel):
    is_enabled: bool


class ReorderBody(BaseModel):
    order: list[str] = Field(..., min_length=1)


def _to_out(server: RdpServer, group_name_map: dict[str, str] | None = None) -> ServerOut:
    name_map = group_name_map or {}
    group_guids = [str(b.ad_group_guid) for b in (server.group_bindings or [])]
    details = [{"guid": g, "cn": name_map.get(g, g)} for g in group_guids]
    return ServerOut(
        id=str(server.id),
        tech_name=server.tech_name,
        display_name=server.display_name,
        address=server.address,
        port=int(server.port),
        is_enabled=bool(server.is_enabled),
        sort_order=int(server.sort_order),
        groups=group_guids,
        group_details=details,
    )


async def _get_server_with_groups(session: AsyncSession, server_id: uuid.UUID) -> RdpServer | None:
    row = await session.execute(
        sa.select(RdpServer).where(RdpServer.id == server_id).options(selectinload(RdpServer.group_bindings))
    )
    return row.scalars().first()


async def _load_group_name_map(session: AsyncSession, servers: list[RdpServer]) -> dict[str, str]:
    guid_set: set[uuid.UUID] = set()
    for server in servers:
        for binding in (server.group_bindings or []):
            guid_set.add(binding.ad_group_guid)
    if not guid_set:
        return {}
    rows = await session.execute(sa.select(AdGroupCache.guid, AdGroupCache.cn).where(AdGroupCache.guid.in_(list(guid_set))))
    return {str(guid): str(cn) for guid, cn in rows.all()}


@router.get("", response_model=list[ServerOut])
async def list_servers(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> list[ServerOut]:
    session = await get_db_session(request)
    try:
        rows = await session.execute(sa.select(RdpServer).options(selectinload(RdpServer.group_bindings)).order_by(RdpServer.sort_order, RdpServer.tech_name))
        servers = list(rows.scalars().all())
        group_name_map = await _load_group_name_map(session, servers)
        return [_to_out(s, group_name_map) for s in servers]
    finally:
        await session.close()


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(
    request: Request,
    body: ServerCreate,
    _: AdminWebSessionData = Depends(require_admin),
) -> ServerOut:
    host, p = _split_address(body.address, body.port)
    groups = _parse_group_guids(body.groups)

    session = await get_db_session(request)
    try:
        srv = RdpServer(
            tech_name=body.tech_name.strip(),
            display_name=body.display_name.strip(),
            address=host,
            port=p,
            is_enabled=bool(body.is_enabled),
            sort_order=int(body.sort_order),
        )
        srv.group_bindings = [ServerGroupBinding(ad_group_guid=g) for g in groups]
        session.add(srv)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            _handle_integrity_error(exc)
        except Exception:
            await session.rollback()
            raise
        created = await _get_server_with_groups(session, srv.id)
        if not created:
            raise HTTPException(status_code=500, detail="Server created but failed to load")
        group_name_map = await _load_group_name_map(session, [created])
        return _to_out(created, group_name_map)
    finally:
        await session.close()


@router.put("/reorder")
async def reorder_servers(
    request: Request,
    body: ReorderBody,
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, str]:
    session = await get_db_session(request)
    try:
        for i, sid in enumerate(body.order):
            try:
                uid = uuid.UUID(str(sid).strip())
            except (ValueError, AttributeError):
                continue
            await session.execute(sa.update(RdpServer).where(RdpServer.id == uid).values(sort_order=i))
        await session.commit()
        return {"status": "ok"}
    finally:
        await session.close()


@router.get("/{server_id}", response_model=ServerOut)
async def get_server(request: Request, server_id: str, _: AdminWebSessionData = Depends(require_admin)) -> ServerOut:
    try:
        sid = uuid.UUID(server_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid server id") from None

    session = await get_db_session(request)
    try:
        row = await session.execute(sa.select(RdpServer).where(RdpServer.id == sid).options(selectinload(RdpServer.group_bindings)))
        srv = row.scalars().first()
        if not srv:
            raise HTTPException(status_code=404, detail="Server not found")
        group_name_map = await _load_group_name_map(session, [srv])
        return _to_out(srv, group_name_map)
    finally:
        await session.close()


@router.put("/{server_id}", response_model=ServerOut)
async def update_server(
    request: Request,
    server_id: str,
    body: ServerUpdate,
    _: AdminWebSessionData = Depends(require_admin),
) -> ServerOut:
    try:
        sid = uuid.UUID(server_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid server id") from None

    session = await get_db_session(request)
    try:
        row = await session.execute(sa.select(RdpServer).where(RdpServer.id == sid).options(selectinload(RdpServer.group_bindings)))
        srv = row.scalars().first()
        if not srv:
            raise HTTPException(status_code=404, detail="Server not found")

        if body.address is not None or body.port is not None:
            host, p = _split_address(body.address or srv.address, body.port if body.port is not None else srv.port)
            srv.address = host
            srv.port = p

        if body.tech_name is not None:
            srv.tech_name = body.tech_name.strip()
        if body.display_name is not None:
            srv.display_name = body.display_name.strip()
        if body.is_enabled is not None:
            srv.is_enabled = bool(body.is_enabled)
        if body.sort_order is not None:
            srv.sort_order = int(body.sort_order)

        if body.groups is not None:
            groups = _parse_group_guids(body.groups)
            srv.group_bindings = [ServerGroupBinding(ad_group_guid=g) for g in groups]

        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            _handle_integrity_error(exc)
        updated = await _get_server_with_groups(session, sid)
        if not updated:
            raise HTTPException(status_code=404, detail="Server not found")
        group_name_map = await _load_group_name_map(session, [updated])
        return _to_out(updated, group_name_map)
    finally:
        await session.close()


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(request: Request, server_id: str, _: AdminWebSessionData = Depends(require_admin)) -> None:
    try:
        sid = uuid.UUID(server_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid server id") from None

    session = await get_db_session(request)
    try:
        row = await session.execute(sa.select(RdpServer).where(RdpServer.id == sid))
        srv = row.scalars().first()
        if not srv:
            raise HTTPException(status_code=404, detail="Server not found")
        await session.delete(srv)
        await session.commit()
    finally:
        await session.close()


@router.post("/{server_id}/clone", response_model=ServerOut)
async def clone_server(request: Request, server_id: str, _: AdminWebSessionData = Depends(require_admin)) -> ServerOut:
    try:
        sid = uuid.UUID(server_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid server id") from None

    session = await get_db_session(request)
    try:
        row = await session.execute(sa.select(RdpServer).where(RdpServer.id == sid).options(selectinload(RdpServer.group_bindings)))
        src = row.scalars().first()
        if not src:
            raise HTTPException(status_code=404, detail="Server not found")

        base_tech = f"{src.tech_name}-copy"
        for attempt in range(1, 6):
            suffix = "" if attempt == 1 else f"-{attempt}"
            new_srv = RdpServer(
                tech_name=f"{base_tech}{suffix}",
                display_name=f"{src.display_name} (копия)",
                address=src.address,
                port=int(src.port),
                is_enabled=bool(src.is_enabled),
                sort_order=int(src.sort_order),
            )
            new_srv.group_bindings = [
                ServerGroupBinding(ad_group_guid=b.ad_group_guid) for b in (src.group_bindings or [])
            ]
            session.add(new_srv)
            try:
                await session.commit()
                cloned = await _get_server_with_groups(session, new_srv.id)
                if not cloned:
                    raise HTTPException(status_code=500, detail="Server cloned but failed to load")
                group_name_map = await _load_group_name_map(session, [cloned])
                return _to_out(cloned, group_name_map)
            except IntegrityError:
                await session.rollback()
                continue
        raise HTTPException(status_code=409, detail="Unable to clone server (tech_name collision)")
    finally:
        await session.close()


@router.patch("/{server_id}/visibility", response_model=ServerOut)
async def set_visibility(
    request: Request,
    server_id: str,
    body: VisibilityPatch,
    _: AdminWebSessionData = Depends(require_admin),
) -> ServerOut:
    try:
        sid = uuid.UUID(server_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid server id") from None

    session = await get_db_session(request)
    try:
        row = await session.execute(sa.select(RdpServer).where(RdpServer.id == sid).options(selectinload(RdpServer.group_bindings)))
        srv = row.scalars().first()
        if not srv:
            raise HTTPException(status_code=404, detail="Server not found")
        srv.is_enabled = bool(body.is_enabled)
        await session.commit()
        updated = await _get_server_with_groups(session, sid)
        if not updated:
            raise HTTPException(status_code=404, detail="Server not found")
        group_name_map = await _load_group_name_map(session, [updated])
        return _to_out(updated, group_name_map)
    finally:
        await session.close()
