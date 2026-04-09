"""Portal service dependency injection helpers."""

from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.loader import AppConfig
from config.settings_manager import SettingsManager
from identity.ldap_auth import LDAPAuthenticator
from redis_store.sessions import SessionStore, WebSessionData

COOKIE_NAME = "rdp_web_session"
CSRF_COOKIE_NAME = "rdp_csrf"


def get_config(request: Request) -> AppConfig:
    cfg: AppConfig | None = getattr(request.app.state, "config", None)
    if cfg is None:
        raise HTTPException(status_code=500, detail="Config not loaded")
    return cfg


def get_settings_manager(request: Request) -> SettingsManager:
    mgr: SettingsManager | None = getattr(request.app.state, "settings_manager", None)
    if mgr is None:
        raise HTTPException(status_code=500, detail="Settings manager not initialized")
    return mgr


def get_session_store(request: Request) -> SessionStore:
    store: SessionStore | None = getattr(request.app.state, "session_store", None)
    if store is None:
        raise HTTPException(status_code=500, detail="Session store not initialized")
    return store


def get_db_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    factory = getattr(request.app.state, "db_sessionmaker", None)
    if factory is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    return factory


def get_ldap(request: Request) -> LDAPAuthenticator:
    ldap: LDAPAuthenticator | None = getattr(request.app.state, "ldap_auth", None)
    if ldap is None:
        raise HTTPException(status_code=503, detail="LDAP not configured")
    return ldap


def is_ldap_configured(request: Request) -> bool:
    return getattr(request.app.state, "ldap_auth", None) is not None


def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def browser_fingerprint(request: Request) -> str:
    parts = [
        request.headers.get("user-agent", ""),
        request.headers.get("sec-ch-ua", ""),
        request.headers.get("sec-ch-ua-platform", ""),
        request.headers.get("accept-language", ""),
    ]
    return "||".join(parts)


def get_current_session(request: Request) -> WebSessionData | None:
    store: SessionStore | None = getattr(request.app.state, "session_store", None)
    if store is None:
        return None
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        return None
    return store.get_web_session(session_id, browser_fingerprint=browser_fingerprint(request))


def require_session(request: Request) -> WebSessionData:
    session = get_current_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


async def get_portal_name(request: Request) -> str:
    """Resolve portal display name from SettingsManager."""
    mgr: SettingsManager | None = getattr(request.app.state, "settings_manager", None)
    if mgr is None:
        return "DC319"
    portal = await mgr.get("portal")
    name = portal.get("name", "DC319") if portal else "DC319"
    return name or "DC319"
