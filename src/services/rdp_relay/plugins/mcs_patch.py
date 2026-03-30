"""MCS patching plugin: fixes serverSelectedProtocol for SSL<->HYBRID bridge."""

from __future__ import annotations

from rdp.mcs import patch_mcs_client, patch_mcs_server
from services.rdp_relay.plugins.base import RdpPlugin, SessionContext


class McsPatchPlugin(RdpPlugin):
    name = "mcs_patch"

    def __init__(self) -> None:
        self._client_first = True
        self._backend_first = True

    async def on_session_start(self, ctx: SessionContext) -> None:
        self._client_first = True
        self._backend_first = True

    async def on_client_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        if self._client_first:
            self._client_first = False
            return patch_mcs_client(data)
        return data

    async def on_backend_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        if self._backend_first:
            self._backend_first = False
            return patch_mcs_server(data)
        return data
