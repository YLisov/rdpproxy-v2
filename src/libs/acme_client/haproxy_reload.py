"""HAProxy Runtime API client for hot SSL certificate update.

Uses the HAProxy stats socket (Unix domain socket) to update a TLS certificate
without restarting the process (HAProxy 2.2+).

Flow:
    1. ``set ssl cert <path> <<\\n<PEM>\\n\\n``  — opens a transaction
    2. ``commit ssl cert <path>``                 — atomically applies the cert

Important: HAProxy's heredoc parser terminates at the first blank line inside the
payload. PEM files produced by some ACME clients contain a blank line between the
end-entity certificate and the intermediate CA certificate. We strip all blank lines
from the PEM content before uploading so that the heredoc is terminated only by our
explicit trailing ``\\n`` (sent via write_eof / SHUT_WR).
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket as _socket

logger = logging.getLogger("rdpproxy.haproxy_reload")

HAPROXY_SOCKET_PATH = "/var/run/haproxy/admin.sock"
HAPROXY_CERT_PATH = "/usr/local/etc/haproxy/certs/rdp.pem"


def _strip_blank_lines(pem: str) -> str:
    """Remove blank lines from PEM content.

    HAProxy's heredoc reader stops at the first empty line, which would truncate
    a fullchain PEM that has a blank line between cert blocks.
    """
    return "\n".join(line for line in pem.splitlines() if line.strip()) + "\n"


def _send_command_sync(socket_path: str, payload: bytes, timeout: float = 15.0) -> str:
    """Low-level synchronous helper: connect, send *payload*, half-close write side, read response."""
    s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(socket_path)
        s.sendall(payload)
        s.shutdown(_socket.SHUT_WR)
        chunks = []
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace").strip()
    finally:
        s.close()


async def hot_update_ssl_cert(
    pem_content: bytes,
    socket_path: str = HAPROXY_SOCKET_PATH,
    haproxy_cert_path: str = HAPROXY_CERT_PATH,
) -> bool:
    """Hot-update an SSL certificate in a running HAProxy instance via Runtime API.

    The function sends a two-phase command to the HAProxy Unix socket:
    first ``set ssl cert`` to stage the new certificate, then ``commit ssl cert``
    to make it active. No HAProxy restart or reload is required.

    Args:
        pem_content: Combined PEM bytes (fullchain + private key), exactly what
            HAProxy uses as its ``crt`` file (i.e. ``rdp.pem``).
        socket_path: Path to the HAProxy stats socket shared via bind mount.
        haproxy_cert_path: Path as HAProxy sees it inside its own container.

    Returns:
        True on success, False if the socket is unavailable or the API reports an error.
    """
    if not os.path.exists(socket_path):
        logger.warning(
            "HAProxy socket not found at %s — skipping hot-update (HAProxy not running yet?)",
            socket_path,
        )
        return False

    loop = asyncio.get_running_loop()

    try:
        cert_str = _strip_blank_lines(pem_content.decode("utf-8"))

        # Abort any stale open transaction first (safe to ignore if none exists).
        abort_payload = f"abort ssl cert {haproxy_cert_path}\n".encode()
        await loop.run_in_executor(None, _send_command_sync, socket_path, abort_payload)

        # Stage the new certificate.
        # The payload is: command line + PEM content + terminating newline (heredoc end).
        set_payload = f"set ssl cert {haproxy_cert_path} <<\n{cert_str}\n".encode()
        set_resp = await loop.run_in_executor(None, _send_command_sync, socket_path, set_payload)
        logger.debug("HAProxy set ssl cert response: %s", set_resp)

        if "Transaction created" not in set_resp and "Transaction updated" not in set_resp:
            logger.error("Unexpected HAProxy response to 'set ssl cert': %s", set_resp)
            return False

        # Commit the staged certificate.
        commit_payload = f"commit ssl cert {haproxy_cert_path}\n".encode()
        commit_resp = await loop.run_in_executor(None, _send_command_sync, socket_path, commit_payload)
        logger.debug("HAProxy commit ssl cert response: %s", commit_resp)

        if "Success" not in commit_resp and "New" not in commit_resp:
            logger.error("Unexpected HAProxy response to 'commit ssl cert': %s", commit_resp)
            return False

        logger.info("HAProxy SSL certificate hot-updated: %s", haproxy_cert_path)
        return True

    except Exception:
        logger.exception("Failed to hot-update HAProxy SSL certificate")
        return False
