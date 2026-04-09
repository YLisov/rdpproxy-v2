"""Admin service dependency injection helpers."""

from __future__ import annotations

import ipaddress
import logging

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.loader import AppConfig
from config.settings_manager import SettingsManager
from redis_store.sessions import AdminWebSessionData, SessionStore

_logger = logging.getLogger("rdpproxy.admin.deps")

ADMIN_COOKIE_NAME = "rdp_admin_session"
ADMIN_CSRF_COOKIE_NAME = "rdp_admin_csrf"


def get_config(request: Request) -> AppConfig:
    cfg: AppConfig | None = getattr(request.app.state, "config", None)
    if cfg is None:
        raise HTTPException(status_code=500, detail="Config not loaded")
    return cfg


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


def get_client_ip(request: Request) -> str:
    ip = getattr(request.state, "client_ip", None)
    if ip:
        return ip
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
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


def _ip_in_networks(ip_str: str, networks: list[str]) -> bool:
    """Check if ip_str belongs to any of the given CIDR networks or exact IPs."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for net_str in networks:
        try:
            net = ipaddress.ip_network(net_str, strict=False)
            if addr in net:
                return True
        except ValueError:
            if ip_str == net_str:
                return True
    return False


def require_admin(request: Request) -> AdminWebSessionData:
    """Dependency that requires a valid admin session. Raises 401 if not authenticated."""
    store = get_session_store(request)
    sid = request.cookies.get(ADMIN_COOKIE_NAME)
    if not sid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    sess = store.get_admin_web_session(sid, browser_fingerprint=browser_fingerprint(request))
    if sess is None:
        raise HTTPException(status_code=401, detail="Session expired")

    client_ip = get_client_ip(request)
    cfg = get_config(request)
    allowed_nets = cfg.admin.allowed_networks
    if allowed_nets and not _ip_in_networks(client_ip, allowed_nets):
        _logger.warning("Admin access denied for IP %s (not in allowed_networks)", client_ip)
        raise HTTPException(status_code=403, detail="Access denied from this IP")

    user_ips = sess.allowed_ips
    if user_ips and not _ip_in_networks(client_ip, user_ips):
        _logger.warning("Admin %s access denied for IP %s (not in user allowed_ips)", sess.username, client_ip)
        raise HTTPException(status_code=403, detail="Access denied from this IP")

    return sess


def get_settings_manager(request: Request) -> SettingsManager:
    mgr: SettingsManager | None = getattr(request.app.state, "settings_manager", None)
    if mgr is None:
        raise HTTPException(status_code=500, detail="Settings manager not initialized")
    return mgr


def get_admin_session_optional(request: Request) -> AdminWebSessionData | None:
    store: SessionStore | None = getattr(request.app.state, "session_store", None)
    if store is None:
        return None
    sid = request.cookies.get(ADMIN_COOKIE_NAME)
    if not sid:
        return None
    return store.get_admin_web_session(sid, browser_fingerprint=browser_fingerprint(request))
