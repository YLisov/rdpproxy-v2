"""TCP utility helpers for the RDP relay: keepalive, abort, buffer tuning."""

from __future__ import annotations

import asyncio
import logging
import socket

logger = logging.getLogger("rdpproxy.relay.tcp")

SOCK_BUF_SIZE = 512 * 1024


def configure_tcp_keepalive(writer: asyncio.StreamWriter) -> None:
    """Set aggressive TCP keepalive and enlarge socket buffers."""
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
        logger.debug("Failed to configure TCP keepalive", exc_info=True)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCK_BUF_SIZE)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCK_BUF_SIZE)
        if hasattr(socket, "TCP_NODELAY"):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except Exception:
        logger.debug("Failed to set socket buffer sizes", exc_info=True)


def tune_writer_buffers(
    writer: asyncio.StreamWriter,
    high_water: int = SOCK_BUF_SIZE,
    low_water: int = 64 * 1024,
) -> None:
    """Raise asyncio transport write-buffer water marks for high throughput."""
    try:
        writer.transport.set_write_buffer_limits(high=high_water, low=low_water)
    except Exception:
        logger.debug("Failed to tune writer buffer limits", exc_info=True)


def abort_writer(writer: asyncio.StreamWriter) -> None:
    """Immediately abort connection, skipping TLS shutdown handshake."""
    try:
        writer.transport.abort()
    except Exception:
        try:
            writer.close()
        except Exception:
            logger.debug("Failed to close writer after abort failure", exc_info=True)
