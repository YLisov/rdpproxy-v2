"""Minimal asyncio HTTP server for ACME HTTP-01 challenge responses."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("rdpproxy.acme.challenge")


class ChallengeServer:
    """Serves ``/.well-known/acme-challenge/<token>`` on port 80."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}
        self._server: asyncio.AbstractServer | None = None

    def set_token(self, token: str, key_authorization: str) -> None:
        self._tokens[token] = key_authorization

    def clear_tokens(self) -> None:
        self._tokens.clear()

    async def start(self, port: int = 80) -> None:
        self._server = await asyncio.start_server(self._handle, "0.0.0.0", port)
        logger.info("ACME challenge server listening on :%d", port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("ACME challenge server stopped")

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=5)
            parts = request_line.decode("ascii", errors="replace").split()
            path = parts[1] if len(parts) >= 2 else ""

            # Consume remaining headers
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line in (b"\r\n", b"\n", b""):
                    break

            prefix = "/.well-known/acme-challenge/"
            if path.startswith(prefix):
                token = path[len(prefix):]
                key_authz = self._tokens.get(token)
                if key_authz:
                    body = key_authz.encode()
                    writer.write(
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: application/octet-stream\r\n"
                        b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                        b"\r\n" + body
                    )
                    await writer.drain()
                    writer.close()
                    return

            writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass
