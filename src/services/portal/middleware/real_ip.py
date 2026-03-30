"""Extract real client IP from X-Real-IP / X-Forwarded-For set by HAProxy."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RealIpMiddleware(BaseHTTPMiddleware):
    """Store resolved client IP in request.state.client_ip for easy access."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        xff = request.headers.get("x-forwarded-for", "")
        real_ip = request.headers.get("x-real-ip", "")
        if real_ip:
            request.state.client_ip = real_ip.strip()
        elif xff:
            request.state.client_ip = xff.split(",")[0].strip()
        elif request.client and request.client.host:
            request.state.client_ip = request.client.host
        else:
            request.state.client_ip = "unknown"
        return await call_next(request)
