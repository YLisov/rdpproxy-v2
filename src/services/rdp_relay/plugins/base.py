"""Base interface for RDP relay plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionContext:
    """Shared state passed to all plugins during an RDP session."""
    connection_id: str = ""
    username: str = ""
    client_ip: str = ""
    target_host: str = ""
    target_port: int = 3389
    instance_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class RdpPlugin:
    """Base interface. Subclasses override needed hooks."""
    name: str = "unnamed"

    async def on_session_start(self, ctx: SessionContext) -> None:
        pass

    async def on_client_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        return data

    async def on_backend_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        return data

    async def on_session_end(self, ctx: SessionContext) -> None:
        pass

    async def on_error(self, error: Exception, ctx: SessionContext) -> None:
        pass
