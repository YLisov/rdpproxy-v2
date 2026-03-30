"""Session activity monitor plugin: detect idle sessions and timeouts."""

from __future__ import annotations

import logging
import time

from services.rdp_relay.plugins.base import RdpPlugin, SessionContext

logger = logging.getLogger("rdpproxy.relay.session_monitor")

DEFAULT_IDLE_TIMEOUT = 3600


class SessionMonitorPlugin(RdpPlugin):
    name = "session_monitor"

    def __init__(self, idle_timeout: int = DEFAULT_IDLE_TIMEOUT) -> None:
        self._idle_timeout = idle_timeout
        self._last_activity: float = 0

    async def on_session_start(self, ctx: SessionContext) -> None:
        self._last_activity = time.monotonic()
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
        return (time.monotonic() - self._last_activity) > self._idle_timeout
