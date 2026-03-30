"""Plugin discovery and execution chain."""

from __future__ import annotations

import logging
from typing import Sequence

from services.rdp_relay.plugins.base import RdpPlugin, SessionContext

logger = logging.getLogger("rdpproxy.relay.plugins")


class PluginRegistry:
    """Manages an ordered list of RdpPlugin instances and dispatches hooks."""

    def __init__(self, plugins: Sequence[RdpPlugin] | None = None) -> None:
        self._plugins: list[RdpPlugin] = list(plugins or [])
        for p in self._plugins:
            logger.info("Registered RDP plugin: %s", p.name)

    async def on_session_start(self, ctx: SessionContext) -> None:
        for p in self._plugins:
            try:
                await p.on_session_start(ctx)
            except Exception:
                logger.exception("Plugin %s on_session_start failed", p.name)

    async def on_client_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        for p in self._plugins:
            try:
                data = await p.on_client_packet(data, ctx)
            except Exception:
                logger.exception("Plugin %s on_client_packet failed", p.name)
        return data

    async def on_backend_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        for p in self._plugins:
            try:
                data = await p.on_backend_packet(data, ctx)
            except Exception:
                logger.exception("Plugin %s on_backend_packet failed", p.name)
        return data

    async def on_session_end(self, ctx: SessionContext) -> None:
        for p in self._plugins:
            try:
                await p.on_session_end(ctx)
            except Exception:
                logger.exception("Plugin %s on_session_end failed", p.name)

    async def on_error(self, error: Exception, ctx: SessionContext) -> None:
        for p in self._plugins:
            try:
                await p.on_error(error, ctx)
            except Exception:
                logger.exception("Plugin %s on_error failed", p.name)
