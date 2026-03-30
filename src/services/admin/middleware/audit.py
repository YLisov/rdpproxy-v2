"""Admin audit middleware: log all mutating API actions."""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from db.models.audit import AdminAuditLog
from services.admin.dependencies import get_admin_session_optional, get_client_ip

logger = logging.getLogger("rdpproxy.admin.audit")


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if not request.url.path.startswith("/api/admin/"):
            return response
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return response

        factory = getattr(request.app.state, "db_sessionmaker", None)
        if factory is None:
            return response

        try:
            admin_sess = get_admin_session_optional(request)
            admin_user = admin_sess.username if admin_sess else "unknown"
            config = getattr(request.app.state, "config", None)
            instance_id = config.instance.id if config else "node-1"
            client_ip = get_client_ip(request)
            action = f"{request.method} {request.url.path}"
            async with factory() as dbs:
                dbs.add(AdminAuditLog(
                    instance_id=instance_id, admin_user=admin_user, action=action,
                    target_type="api", target_id=request.url.path,
                    client_ip=client_ip, new_value={"status_code": response.status_code},
                ))
                await dbs.commit()
        except Exception:
            logger.exception("Failed to write admin audit log")
        return response
