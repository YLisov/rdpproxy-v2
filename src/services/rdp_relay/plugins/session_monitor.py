"""Session activity monitor plugin: detect idle sessions and absolute duration limits."""

from __future__ import annotations

import logging
import time

from services.rdp_relay.plugins.base import RdpPlugin, SessionContext

logger = logging.getLogger("rdpproxy.relay.session_monitor")

DEFAULT_IDLE_TIMEOUT = 3600
DEFAULT_MAX_SESSION_DURATION = 0


class SessionMonitorPlugin(RdpPlugin):
    name = "session_monitor"

    def __init__(
        self,
        idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
        max_session_duration: int = DEFAULT_MAX_SESSION_DURATION,
    ) -> None:
        self._idle_timeout = idle_timeout
        self._max_session_duration = max_session_duration
        self._last_activity: float = 0
        self._started_at: float = 0

    def update_timeouts(self, idle_timeout: int, max_session_duration: int) -> None:
        self._idle_timeout = idle_timeout
        self._max_session_duration = max_session_duration

    async def on_session_start(self, ctx: SessionContext) -> None:
        now = time.monotonic()
        self._last_activity = now
        self._started_at = now
        logger.info("Session monitor started for %s", ctx.connection_id)

    async def on_client_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        self._last_activity = time.monotonic()
        return data

    async def on_backend_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        self._last_activity = time.monotonic()
        return data

    async def on_session_end(self, ctx: SessionContext) -> None:
        duration = time.monotonic() - self._last_activity
        logger.info("Session %s ended, idle for %.1fs before end", ctx.connection_id, duration)

    def is_idle(self) -> bool:
        return self._idle_timeout > 0 and (time.monotonic() - self._last_activity) > self._idle_timeout

    def is_duration_exceeded(self) -> bool:
        if self._max_session_duration <= 0:
            return False
        return (time.monotonic() - self._started_at) > self._max_session_duration
