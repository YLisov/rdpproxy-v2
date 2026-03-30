"""TCP utility helpers for the RDP relay: keepalive, abort."""

from __future__ import annotations

import asyncio
import socket


def configure_tcp_keepalive(writer: asyncio.StreamWriter) -> None:
    """Set aggressive TCP keepalive on the transport socket."""
    sock = writer.get_extra_info("socket")
    if sock is None:
        return
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "TCP_KEEPIDLE"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
        if hasattr(socket, "TCP_KEEPINTVL"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
        if hasattr(socket, "TCP_KEEPCNT"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        if hasattr(socket, "TCP_USER_TIMEOUT"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_USER_TIMEOUT, 45000)
    except Exception:
        pass


def abort_writer(writer: asyncio.StreamWriter) -> None:
    """Immediately abort connection, skipping TLS shutdown handshake."""
    try:
        writer.transport.abort()
    except Exception:
        try:
            writer.close()
        except Exception:
            pass
