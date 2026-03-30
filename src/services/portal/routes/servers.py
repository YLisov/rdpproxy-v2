"""Portal server listing and .rdp download routes."""

from __future__ import annotations

import secrets
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import selectinload

from db.models.server import RdpServer
from rdp.rdp_file import build_rdp_content
from services.portal.dependencies import (
    CSRF_COOKIE_NAME,
    browser_fingerprint,
    get_config,
    get_current_session,
    get_db_sessionmaker,
    get_session_store,
    require_session,
)

router = APIRouter()


def _server_visible(server_group_guids: list[str], user_group_guids: list[str]) -> bool:
    if not server_group_guids:
        return True
    grp_set = {str(v).strip().lower() for v in user_group_guids if str(v).strip()}
    srv_set = {str(v).strip().lower() for v in server_group_guids if str(v).strip()}
    return bool(grp_set.intersection(srv_set))


async def _list_visible_servers(request: Request, user_group_guids: list[str]) -> list[dict[str, Any]]:
    factory = get_db_sessionmaker(request)
    async with factory() as dbs:
        rows = await dbs.execute(
            sa.select(RdpServer)
            .where(RdpServer.is_enabled.is_(True))
            .options(selectinload(RdpServer.group_bindings))
            .order_by(RdpServer.sort_order, RdpServer.tech_name)
        )
        servers = list(rows.scalars().all())
        visible: list[dict[str, Any]] = []
        for s in servers:
            server_guids = [str(b.ad_group_guid) for b in (s.group_bindings or [])]
            if not _server_visible(server_guids, user_group_guids):
                continue
            visible.append({"id": s.tech_name, "name": s.display_name, "host": s.address, "port": int(s.port), "groups": server_guids})
        return visible


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    templates = request.app.state.templates
    session = get_current_session(request)
    if not session:
        csrf_token = request.cookies.get(CSRF_COOKIE_NAME) or secrets.token_urlsafe(24)
        response = templates.TemplateResponse(
            request, "login.html",
            {"session": None, "servers": [], "error": None, "csrf_token": csrf_token},
        )
        response.set_cookie(key=CSRF_COOKIE_NAME, value=csrf_token, httponly=False, secure=False, samesite="lax", max_age=600)
        return response
    visible = await _list_visible_servers(request, session.group_guids)
    return templates.TemplateResponse(
        request, "login.html",
        {"session": session, "servers": visible, "error": None, "csrf_token": None},
    )


@router.get("/rdp/{server_id}")
async def rdp_download(request: Request, server_id: str) -> PlainTextResponse:
    session = require_session(request)
    store = get_session_store(request)
    factory = get_db_sessionmaker(request)
    cfg = get_config(request)

    async with factory() as dbs:
        row = await dbs.execute(
            sa.select(RdpServer)
            .where(RdpServer.tech_name == server_id)
            .options(selectinload(RdpServer.group_bindings))
        )
        s = row.scalars().first()
    if not s or not s.is_enabled:
        raise HTTPException(status_code=404, detail="Server not found")

    server_guids = [str(b.ad_group_guid) for b in (s.group_bindings or [])]
    if not _server_visible(server_guids, session.group_guids):
        raise HTTPException(status_code=403, detail="Access denied")

    token = store.create_session(
        username=session.username, password=session.password,
        target_host=s.address, target_port=int(s.port),
        server_id=str(s.id), server_display=s.display_name,
    )
    async with factory() as dbs:
        content = await build_rdp_content(
            db_session=dbs, user_group_guids=session.group_guids,
            proxy_host=cfg.proxy.public_host, proxy_port=cfg.proxy.listen_port, token=token,
        )
    headers = {"Content-Disposition": f'attachment; filename="{server_id}.rdp"'}
    return PlainTextResponse(content=content, media_type="application/x-rdp", headers=headers)
