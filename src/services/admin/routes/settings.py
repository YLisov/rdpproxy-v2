from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.settings import PortalSetting
from identity.ldap_auth import LDAPAuthenticator
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_config, get_db_sessionmaker, require_admin

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])

_MERGE_KEYS = frozenset({"ldap", "security", "proxy", "admin_security", "redis", "portal"})


class SettingsPayload(BaseModel):
    values: dict[str, Any]


async def _db(request: Request) -> AsyncSession:
    return get_db_sessionmaker(request)()


@router.get("")
async def get_settings(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, Any]:
    session = await _db(request)
    try:
        rows = await session.execute(sa.select(PortalSetting))
        out: dict[str, Any] = {}
        for r in rows.scalars().all():
            out[r.key] = r.value
        # include current runtime config for convenience
        cfg = get_config(request)
        out.setdefault("ldap", cfg.ldap.model_dump())
        out.setdefault("security", cfg.security.model_dump())
        out.setdefault("proxy", cfg.proxy.model_dump())
        out.setdefault("portal", {"name": "DC319"})
        return out
    finally:
        await session.close()


def _clean_dict(v: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kk, vv in v.items():
        if vv is None:
            continue
        if isinstance(vv, str) and not vv.strip():
            continue
        out[kk] = vv
    return out


@router.put("")
async def put_settings(request: Request, body: SettingsPayload, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, str]:
    session = await _db(request)
    try:
        for k, v in (body.values or {}).items():
            key = str(k).strip()
            if not key:
                continue
            row = await session.get(PortalSetting, key)
            if isinstance(v, dict) and key in _MERGE_KEYS:
                patch = _clean_dict(v)
                if row is None:
                    session.add(PortalSetting(key=key, value=patch))
                else:
                    old = row.value if isinstance(row.value, dict) else {}
                    row.value = {**dict(old), **patch}
            else:
                if row is None:
                    row = PortalSetting(key=key, value=v if isinstance(v, dict) else {"value": v})
                    session.add(row)
                else:
                    row.value = v if isinstance(v, dict) else {"value": v}
        await session.commit()
        reapply = getattr(request.app.state, "reapply_portal_settings", None)
        if callable(reapply):
            try:
                await reapply()
            except Exception:
                pass
        return {"status": "ok"}
    finally:
        await session.close()


@router.post("/ldap-check")
async def ldap_check(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> dict[str, str]:
    ldap: LDAPAuthenticator | None = getattr(request.app.state, "ldap_auth", None)
    if ldap is None:
        raise HTTPException(status_code=500, detail="LDAP is not initialized")
    # Try a benign operation using service bind.
    try:
        ldap.list_groups(limit=1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"LDAP check failed: {exc}") from None
    return {"status": "ok"}
