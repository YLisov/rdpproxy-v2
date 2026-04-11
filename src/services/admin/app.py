"""Admin FastAPI application factory."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
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
        name = portal.get("name", "RDP-Proxy") if portal else "RDP-Proxy"
        app.state.portal_name_cache = name or "RDP-Proxy"
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

    app.state._prev_public_host: str | None = None
    app.state._prev_public_port: int | None = None
    app.state.cert_status: dict[str, Any] = {"status": "idle", "message": "", "domain": ""}

    def _update_dotenv_port(port: int) -> bool:
        """Update PUBLIC_PORT in the .env file (in-place write). Returns True on success."""
        env_path = os.environ.get("DOTENV_PATH", "/app/.env")
        lines: list[str] = []
        found = False
        try:
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("PUBLIC_PORT="):
                        lines.append(f"PUBLIC_PORT={port}\n")
                        found = True
                    else:
                        lines.append(line)
        except FileNotFoundError:
            pass
        if not found:
            lines.append(f"PUBLIC_PORT={port}\n")
        try:
            with open(env_path, "w") as f:
                f.writelines(lines)
            logger.info("Updated %s: PUBLIC_PORT=%d", env_path, port)
            return True
        except OSError:
            logger.warning("Failed to write PUBLIC_PORT to %s", env_path, exc_info=True)
            return False

    async def _request_certificate(domain: str) -> None:
        """Background task: request an SSL certificate via ACME."""
        from acme_client import obtain_certificate
        from acme_client.haproxy_reload import hot_update_ssl_cert

        app.state.cert_status = {"status": "in_progress", "message": "Requesting certificate...", "domain": domain}
        certs_dir = os.environ.get("CERTS_DIR", "/app/certs")
        result = await obtain_certificate(domain=domain, email=None, certs_dir=certs_dir)
        if result.success:
            haproxy_msg = ""
            haproxy_socket = os.environ.get("HAPROXY_SOCKET", "/var/run/haproxy/admin.sock")
            try:
                with open(result.haproxy_pem_path, "rb") as _f:
                    pem_bytes = _f.read()
                reloaded = await hot_update_ssl_cert(pem_bytes, socket_path=haproxy_socket)
                if reloaded:
                    haproxy_msg = " HAProxy обновлён автоматически."
                    logger.info("HAProxy SSL hot-updated after certificate renewal for %s", domain)
                else:
                    haproxy_msg = " Выполните: docker compose restart haproxy"
            except Exception:
                logger.warning("Could not hot-update HAProxy SSL cert", exc_info=True)
                haproxy_msg = " Выполните: docker compose restart haproxy"
            app.state.cert_status = {
                "status": "success",
                "message": f"Certificate for {domain} obtained.{haproxy_msg}",
                "domain": domain,
            }
        else:
            app.state.cert_status = {
                "status": "error",
                "message": result.message or result.error,
                "domain": domain,
            }

    async def _cert_renewal_loop() -> None:
        """Background task: auto-renew the TLS certificate 30 days before expiry."""
        while True:
            await asyncio.sleep(12 * 3600)
            try:
                domain = (app.state._prev_public_host or "").strip()
                if not domain:
                    continue
                certs_dir = os.environ.get("CERTS_DIR", "/app/certs")
                from acme_client import cert_days_remaining
                days = cert_days_remaining(certs_dir)
                if days is None:
                    logger.info("Cert renewal loop: no certificate found for %s, requesting", domain)
                    await _request_certificate(domain)
                elif days < 30:
                    logger.info(
                        "Cert renewal loop: certificate for %s expires in %d days, renewing",
                        domain, days,
                    )
                    await _request_certificate(domain)
                else:
                    logger.debug("Cert renewal loop: certificate for %s valid for %d more days", domain, days)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Cert renewal loop error")

    async def _on_proxy_change(data: dict[str, Any]) -> None:
        new_host = (data.get("public_host") or "").strip()
        prev = app.state._prev_public_host
        app.state._prev_public_host = new_host
        if new_host and prev and new_host != prev:
            logger.info("public_host changed: %s -> %s, requesting certificate", prev, new_host)
            asyncio.create_task(_request_certificate(new_host))

        new_port = data.get("public_port") or data.get("listen_port")
        if new_port is not None:
            new_port = int(new_port)
            prev_port = app.state._prev_public_port
            app.state._prev_public_port = new_port
            if prev_port is not None and new_port != prev_port:
                logger.info("public_port changed: %d -> %d, updating .env", prev_port, new_port)
                _update_dotenv_port(new_port)

    settings_mgr.on_change("ldap", _on_ldap_change)
    settings_mgr.on_change("redis_ttl", _on_redis_ttl_change)
    settings_mgr.on_change("portal", _on_portal_change)
    settings_mgr.on_change("proxy", _on_proxy_change)

    async def _reapply_portal_settings() -> None:
        await settings_mgr.load()
        await _on_ldap_change({})
        await _on_redis_ttl_change(settings_mgr.redis_ttl)
        app.state.portal_name_cache = None
        proxy = settings_mgr.proxy_params
        app.state._prev_public_host = (proxy.get("public_host") or "").strip()
        app.state._prev_public_port = proxy.get("public_port") or proxy.get("listen_port")
        if app.state._prev_public_port is not None:
            app.state._prev_public_port = int(app.state._prev_public_port)

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
        proxy = settings_mgr.proxy_params
        app.state._prev_public_host = (proxy.get("public_host") or "").strip()
        app.state._prev_public_port = proxy.get("public_port") or proxy.get("listen_port")
        if app.state._prev_public_port is not None:
            app.state._prev_public_port = int(app.state._prev_public_port)
        os.write(2, json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": "INFO", "logger": "rdpproxy.admin",
            "msg": f"Settings loaded (public_host={app.state._prev_public_host}, public_port={app.state._prev_public_port})",
            "service": "admin",
        }, ensure_ascii=False).encode() + b"\n")
        app.state._renewal_task = asyncio.create_task(_cert_renewal_loop())

        async def _startup_cert_check() -> None:
            await asyncio.sleep(60)
            try:
                domain = (app.state._prev_public_host or "").strip()
                if not domain:
                    return
                certs_dir = os.environ.get("CERTS_DIR", "/app/certs")
                from acme_client import cert_days_remaining
                days = cert_days_remaining(certs_dir)
                if days is not None and days < 30:
                    logger.info(
                        "Startup cert check: certificate for %s expires in %d days, renewing",
                        domain, days,
                    )
                    await _request_certificate(domain)
            except Exception:
                logger.exception("Startup certificate check error")

        asyncio.create_task(_startup_cert_check())

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
        task = getattr(app.state, "_renewal_task", None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
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
