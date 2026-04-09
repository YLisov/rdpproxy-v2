from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from config.loader import LdapConfig
from config.settings_manager import SettingsManager
from identity.ldap_auth import LDAPAuthenticator
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_redis_client, get_settings_manager, require_admin

router = APIRouter(prefix="/api/admin/settings", tags=["admin-settings"])
logger = logging.getLogger("rdpproxy.admin.settings")

_MERGE_KEYS = frozenset({
    "ldap", "security", "proxy",
    "redis_ttl", "portal", "dns", "relay",
})


class SettingsPayload(BaseModel):
    values: dict[str, Any]


def _clean_dict(v: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kk, vv in v.items():
        if vv is None:
            continue
        if isinstance(vv, str) and not vv.strip():
            continue
        out[kk] = vv
    return out


@router.get("")
async def get_settings(
    request: Request,
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, Any]:
    mgr = get_settings_manager(request)
    return mgr.get_all_for_ui()


@router.put("")
async def put_settings(
    request: Request,
    body: SettingsPayload,
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, str]:
    mgr = get_settings_manager(request)
    redis_client = get_redis_client(request)

    _ALLOWED_KEYS = _MERGE_KEYS | {"instance"}
    for k, v in (body.values or {}).items():
        key = str(k).strip()
        if not key:
            continue
        if key not in _ALLOWED_KEYS:
            raise HTTPException(status_code=400, detail=f"Unknown setting key: {key}")
        if not isinstance(v, dict):
            v = {"value": v}
        if key in _MERGE_KEYS:
            v = _clean_dict(v)

        await mgr.save(key, v, publish_redis=redis_client)

    reapply = getattr(request.app.state, "reapply_portal_settings", None)
    if callable(reapply):
        try:
            await reapply()
        except Exception:
            logger.warning("reapply_portal_settings failed", exc_info=True)

    return {"status": "ok"}


@router.post("/ldap-check")
async def ldap_check(
    request: Request,
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, str]:
    ldap: LDAPAuthenticator | None = getattr(request.app.state, "ldap_auth", None)
    if ldap is None:
        raise HTTPException(status_code=500, detail="LDAP is not initialized")
    try:
        ldap.list_groups(limit=1)
    except Exception as exc:
        logger.warning("LDAP check failed: %s", exc)
        raise HTTPException(status_code=400, detail="Проверка LDAP завершилась ошибкой") from None
    return {"status": "ok"}


@router.post("/ldap-test")
async def ldap_test(
    request: Request,
    body: SettingsPayload,
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, str]:
    """Validate LDAP connectivity with the provided (unsaved) settings."""
    mgr = get_settings_manager(request)
    current = await mgr.get("ldap")
    merged = {**current, **_clean_dict(body.values.get("ldap", {}))}
    merged.pop("bind_password_enc", None)
    try:
        cfg = LdapConfig(**merged)
    except Exception as exc:
        logger.warning("Invalid LDAP config: %s", exc)
        raise HTTPException(status_code=400, detail="Некорректная конфигурация LDAP") from None
    try:
        test_ldap = LDAPAuthenticator(cfg)
        test_ldap.list_groups(limit=1)
    except Exception as exc:
        logger.warning("LDAP test failed: %s", exc)
        raise HTTPException(status_code=400, detail="Тест подключения LDAP завершился ошибкой") from None
    return {"status": "ok"}
