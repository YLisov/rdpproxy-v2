"""Portal FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.loader import AppConfig
from config.settings_manager import SettingsManager
from db.engine import create_engine, create_sessionmaker
from db.models.admin_user import AdminUser
from identity.ldap_auth import LDAPAuthenticator
from redis_store.client import create_redis_client
from redis_store.sessions import SessionStore
from security.passwords import hash_password

from services.portal.middleware.correlation_id import CorrelationIdMiddleware
from services.portal.middleware.real_ip import RealIpMiddleware
from services.portal.middleware.security_headers import SecurityHeadersMiddleware
from services.portal.routes import auth, health, servers

logger = logging.getLogger("rdpproxy.portal")
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASSETS_DIR = PROJECT_ROOT / "assets"


def create_app(config: AppConfig) -> FastAPI:
    """Build and configure the Portal FastAPI app."""
    app = FastAPI(title="RDP Proxy Portal", docs_url=None, redoc_url=None)

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

    if ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RealIpMiddleware)

    app.include_router(auth.router)
    app.include_router(servers.router)
    app.include_router(health.router)

    async def _on_ldap_change(_data: dict[str, Any]) -> None:
        ldap = settings_mgr.ldap
        app.state.ldap_auth = LDAPAuthenticator(ldap) if ldap else None

    async def _on_redis_ttl_change(data: dict[str, Any]) -> None:
        store: SessionStore = app.state.session_store
        store.web_ttl = data.get("web_session_ttl", store.web_ttl)
        store.rdp_token_ttl = data.get("rdp_token_ttl", store.rdp_token_ttl)
        store.web_idle_ttl = data.get("web_idle_ttl", store.web_idle_ttl)

    settings_mgr.on_change("ldap", _on_ldap_change)
    settings_mgr.on_change("redis_ttl", _on_redis_ttl_change)

    @app.on_event("startup")
    async def _bootstrap() -> None:
        await settings_mgr.load()
        ldap = settings_mgr.ldap
        app.state.ldap_auth = LDAPAuthenticator(ldap) if ldap else None
        ttl = settings_mgr.redis_ttl
        store: SessionStore = app.state.session_store
        store.web_ttl = ttl.get("web_session_ttl", store.web_ttl)
        store.rdp_token_ttl = ttl.get("rdp_token_ttl", store.rdp_token_ttl)
        store.web_idle_ttl = ttl.get("web_idle_ttl", store.web_idle_ttl)

        await _bootstrap_default_admin(app)
        asyncio.create_task(_settings_listener(app))
        logger.info("Portal service settings loaded from DB")

    @app.on_event("shutdown")
    async def _cleanup() -> None:
        if app.state.db_engine:
            await app.state.db_engine.dispose()

    return app


async def _settings_listener(app: FastAPI) -> None:
    """Background task: listen for settings changes via Redis pub/sub."""
    try:
        pubsub = app.state.redis_client.pubsub()
        pubsub.subscribe("rdp:settings:changed")
        while True:
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg["type"] == "message":
                mgr: SettingsManager = app.state.settings_manager
                await mgr.load()
                ldap = mgr.ldap
                app.state.ldap_auth = LDAPAuthenticator(ldap) if ldap else None
                ttl = mgr.redis_ttl
                store: SessionStore = app.state.session_store
                store.web_ttl = ttl.get("web_session_ttl", store.web_ttl)
                store.rdp_token_ttl = ttl.get("rdp_token_ttl", store.rdp_token_ttl)
                store.web_idle_ttl = ttl.get("web_idle_ttl", store.web_idle_ttl)
                logger.info("Portal reloaded settings after pub/sub notification")
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Settings listener crashed")


async def _bootstrap_default_admin(app: FastAPI) -> None:
    """Create default admin account if no admins exist."""
    factory = getattr(app.state, "db_sessionmaker", None)
    if factory is None:
        return
    async with factory() as dbs:
        cnt = await dbs.scalar(sa.select(sa.func.count(AdminUser.id)))
        if cnt and int(cnt) > 0:
            return
        dbs.add(AdminUser(
            username="admin", password_hash=hash_password("admin"),
            is_active=True, must_change_password=True, allowed_ips=[],
        ))
        await dbs.commit()
        logger.warning("Created default admin user 'admin' — change password on first login")
