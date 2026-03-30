"""Portal FastAPI application factory."""

from __future__ import annotations

import logging
from pathlib import Path

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from config.loader import AppConfig
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
    app.state.ldap_auth = LDAPAuthenticator(config.ldap)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(RealIpMiddleware)

    app.include_router(auth.router)
    app.include_router(servers.router)
    app.include_router(health.router)

    @app.on_event("startup")
    async def _bootstrap() -> None:
        await _bootstrap_default_admin(app)

    @app.on_event("shutdown")
    async def _cleanup() -> None:
        if app.state.db_engine:
            await app.state.db_engine.dispose()

    return app


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
