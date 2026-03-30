"""Bidirectional TCP relay with plugin hooks for data transformation."""

from __future__ import annotations

import asyncio
import logging
import ssl
from dataclasses import dataclass

from services.rdp_relay.plugins.base import SessionContext
from services.rdp_relay.plugins.registry import PluginRegistry
from services.rdp_relay.tcp_utils import abort_writer

logger = logging.getLogger("rdpproxy.relay.pipe")
READ_CHUNK = 65536
POLL_TIMEOUT = 1.0


@dataclass(frozen=True)
class LegResult:
    direction: str
    transferred: int
    reason: str


async def _pipe(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    direction: str,
    *,
    plugins: PluginRegistry,
    ctx: SessionContext,
    kill_checker=None,
) -> LegResult:
    """One-way data pump with plugin transformation hooks."""
    transferred = 0
    reason = "eof"
    is_client_to_backend = direction == "client->backend"
    try:
        while True:
            if kill_checker is not None and kill_checker():
                reason = "killed"
                break
            try:
                data = await asyncio.wait_for(reader.read(READ_CHUNK), timeout=POLL_TIMEOUT)
            except asyncio.TimeoutError:
                continue
            if not data:
                break
            if is_client_to_backend:
                data = await plugins.on_client_packet(data, ctx)
            else:
                data = await plugins.on_backend_packet(data, ctx)
            transferred += len(data)
            writer.write(data)
            await writer.drain()
    except asyncio.IncompleteReadError:
        reason = "incomplete-read"
    except ssl.SSLError as e:
        reason = f"ssl-error:{e.reason}"
    except ConnectionError as e:
        reason = f"connection-error:{e}"
    except TimeoutError:
        reason = "ssl-shutdown-timeout"
    except Exception as e:
        reason = f"error:{type(e).__name__}:{e}"
    return LegResult(direction=direction, transferred=transferred, reason=reason)


@dataclass(frozen=True)
class RelayResult:
    bytes_to_client: int
    bytes_to_backend: int
    legs: list[LegResult]


async def relay_bidirectional(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    backend_reader: asyncio.StreamReader,
    backend_writer: asyncio.StreamWriter,
    *,
    plugins: PluginRegistry,
    ctx: SessionContext,
    kill_checker=None,
) -> RelayResult:
    """Run two pipes and stop relay when any direction is closed."""
    logger.info("Relay starting for %s", ctx.connection_id)
    tasks = [
        asyncio.create_task(
            _pipe(
                client_reader, backend_writer, "client->backend",
                plugins=plugins, ctx=ctx, kill_checker=kill_checker,
            )
        ),
        asyncio.create_task(
            _pipe(
                backend_reader, client_writer, "backend->client",
                plugins=plugins, ctx=ctx, kill_checker=kill_checker,
            )
        ),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    abort_writer(client_writer)
    abort_writer(backend_writer)
    results = await asyncio.gather(*tasks, return_exceptions=True)

    bytes_to_backend = 0
    bytes_to_client = 0
    legs: list[LegResult] = []
    for item in results:
        if isinstance(item, LegResult):
            legs.append(item)
            if item.direction == "client->backend":
                bytes_to_backend = item.transferred
            else:
                bytes_to_client = item.transferred
            logger.info("Relay leg %s closed: bytes=%d reason=%s", item.direction, item.transferred, item.reason)
        elif isinstance(item, BaseException):
            logger.warning("Relay pipe exception: %s", item)

    return RelayResult(bytes_to_client=bytes_to_client, bytes_to_backend=bytes_to_backend, legs=legs)
