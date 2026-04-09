"""CSRF protection middleware for admin JSON API endpoints.

Requires mutating requests (POST/PUT/DELETE/PATCH) on /api/ paths
to include a valid Origin header matching the Host, or an
X-Requested-With header (set by fetch/XHR).
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("rdpproxy.admin.csrf")

_MUTATING_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        origin = request.headers.get("origin", "")
        if origin:
            parsed = urlparse(origin)
            host_header = request.headers.get("host", "")
            if parsed.netloc and parsed.netloc != host_header:
                logger.warning("CSRF: Origin %s does not match Host %s", origin, host_header)
                return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
            return await call_next(request)

        if request.headers.get("x-requested-with"):
            return await call_next(request)

        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            return await call_next(request)

        logger.warning("CSRF: no Origin/X-Requested-With/JSON content-type for %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
