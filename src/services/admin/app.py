"""Admin FastAPI application factory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from config.loader import AppConfig
from config.settings_manager import SettingsManager
from db.engine import create_engine, create_sessionmaker
from identity.ldap_auth import LDAPAuthenticator
from redis_store.client import create_redis_client
from redis_store.sessions import AdminWebSessionData, SessionStore
from services.admin.dependencies import ADMIN_COOKIE_NAME, browser_fingerprint, require_admin

from services.admin.middleware.audit import AuditMiddleware
from services.admin.middleware.csrf import CsrfMiddleware
from services.portal.middleware.security_headers import SecurityHeadersMiddleware
from services.admin.routes import (
    ad_groups,
    admin_users,
    auth,
    cluster,
    servers,
    services_mgmt,
    sessions,
    settings,
    stats,
    templates,
)

logger = logging.getLogger("rdpproxy.admin")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def create_app(config: AppConfig) -> FastAPI:
    """Build and configure the Admin FastAPI app."""
    app = FastAPI(title="RDP Proxy Admin", docs_url=None, redoc_url=None)

    app.state.config = config
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    engine = create_engine(config.database)
    app.state.db_engine = engine
    app.state.db_sessionmaker = create_sessionmaker(engine)

    redis_client = create_redis_client(config.redis)
    app.state.redis_client = redis_client
    app.state.session_store = SessionStore(redis_client, config.redis, config.security)

    ldap_cfg = config.ldap
    app.state.ldap_auth = LDAPAuthenticator(ldap_cfg) if ldap_cfg else None

    settings_mgr = SettingsManager(app.state.db_sessionmaker, config, config.security.encryption_key)
    app.state.settings_manager = settings_mgr

    app.state.portal_name_cache: str | None = None

    async def _load_portal_name() -> str:
        cached = app.state.portal_name_cache
        if cached is not None:
            return cached
        portal = await settings_mgr.get("portal")
        name = portal.get("name", "DC319") if portal else "DC319"
        app.state.portal_name_cache = name or "DC319"
        return app.state.portal_name_cache

    app.state.load_portal_name = _load_portal_name

    async def _on_ldap_change(_data: dict[str, Any]) -> None:
        ldap = settings_mgr.ldap
        if ldap:
            app.state.ldap_auth = LDAPAuthenticator(ldap)
            logger.info("LDAP authenticator reloaded from DB settings")
        else:
            app.state.ldap_auth = None

    async def _on_redis_ttl_change(data: dict[str, Any]) -> None:
        store: SessionStore = app.state.session_store
        store.web_ttl = data.get("web_session_ttl", store.web_ttl)
        store.rdp_token_ttl = data.get("rdp_token_ttl", store.rdp_token_ttl)
        store.web_idle_ttl = data.get("web_idle_ttl", store.web_idle_ttl)
        logger.info("Session TTLs updated from DB settings")

    async def _on_portal_change(_data: dict[str, Any]) -> None:
        app.state.portal_name_cache = None

    settings_mgr.on_change("ldap", _on_ldap_change)
    settings_mgr.on_change("redis_ttl", _on_redis_ttl_change)
    settings_mgr.on_change("portal", _on_portal_change)

    async def _reapply_portal_settings() -> None:
        await settings_mgr.load()
        await _on_ldap_change({})
        await _on_redis_ttl_change(settings_mgr.redis_ttl)
        app.state.portal_name_cache = None

    app.state.reapply_portal_settings = _reapply_portal_settings

    @app.on_event("startup")
    async def _load_settings() -> None:
        await settings_mgr.load()
        ldap = settings_mgr.ldap
        if ldap:
            app.state.ldap_auth = LDAPAuthenticator(ldap)
        ttl = settings_mgr.redis_ttl
        store: SessionStore = app.state.session_store
        store.web_ttl = ttl.get("web_session_ttl", store.web_ttl)
        store.rdp_token_ttl = ttl.get("rdp_token_ttl", store.rdp_token_ttl)
        store.web_idle_ttl = ttl.get("web_idle_ttl", store.web_idle_ttl)
        logger.info("Admin service settings loaded from DB")

    app.add_middleware(AuditMiddleware)
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.exception_handler(HTTPException)
    async def _html_unauthorized(request: Request, exc: HTTPException):
        if exc.status_code == 401 and request.url.path.startswith("/admin") and not request.url.path.startswith("/api/"):
            return RedirectResponse(url="/admin/login", status_code=303)
        from fastapi.exception_handlers import http_exception_handler
        return await http_exception_handler(request, exc)

    app.include_router(auth.router, prefix="/admin")
    app.include_router(servers.router)
    app.include_router(templates.router)
    app.include_router(settings.router)
    app.include_router(sessions.router)
    app.include_router(stats.router)
    app.include_router(admin_users.router)
    app.include_router(ad_groups.router)
    app.include_router(cluster.router)
    app.include_router(services_mgmt.router)

    _register_html_pages(app)

    @app.on_event("shutdown")
    async def _cleanup() -> None:
        if app.state.db_engine:
            await app.state.db_engine.dispose()

    return app


def _register_html_pages(app: FastAPI) -> None:
    """Register HTML page routes for the admin panel."""

    from fastapi import Depends

    @app.get("/admin")
    async def admin_root(_: AdminWebSessionData = Depends(require_admin)) -> RedirectResponse:
        return RedirectResponse(url="/admin/dashboard", status_code=302)

    page_routes = [
        ("/admin/dashboard", "admin_dashboard.html", "dashboard"),
        ("/admin/servers", "admin_servers.html", "servers"),
        ("/admin/templates", "admin_templates.html", "templates"),
        ("/admin/settings", "admin_settings.html", "settings"),
        ("/admin/sessions", "admin_sessions.html", "sessions"),
        ("/admin/history", "admin_history.html", "history"),
    ]

    for path, template_name, nav_key in page_routes:

        def _make_handler(tpl: str, nav: str):
            async def handler(request: Request, admin: AdminWebSessionData = Depends(require_admin)):
                portal_name = await app.state.load_portal_name()
                return app.state.templates.TemplateResponse(request, tpl, {"admin": admin, "active_nav": nav, "portal_name": portal_name})
            return handler

        app.add_api_route(path, _make_handler(template_name, nav_key), methods=["GET"])
