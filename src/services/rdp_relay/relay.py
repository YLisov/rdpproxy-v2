"""Bidirectional TCP relay with plugin hooks for data transformation."""

from __future__ import annotations

import asyncio
import logging
import ssl
from dataclasses import dataclass
from typing import Callable

from services.rdp_relay.plugins.base import SessionContext
from services.rdp_relay.plugins.registry import PluginRegistry
from services.rdp_relay.tcp_utils import abort_writer, tune_writer_buffers

logger = logging.getLogger("rdpproxy.relay.pipe")
READ_CHUNK = 131072
WRITE_HIGH_WATER = 512 * 1024
WRITE_LOW_WATER = 64 * 1024
KILL_CHECK_INTERVAL = 2.0


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
    kill_event: asyncio.Event | None = None,
) -> LegResult:
    """One-way data pump with plugin transformation hooks."""
    tune_writer_buffers(writer, WRITE_HIGH_WATER, WRITE_LOW_WATER)
    transferred = 0
    reason = "eof"
    is_client_to_backend = direction == "client->backend"
    try:
        while True:
            if kill_event is not None and kill_event.is_set():
                reason = "killed"
                break
            data = await reader.read(READ_CHUNK)
            if not data:
                break
            if is_client_to_backend:
                data = await plugins.on_client_packet(data, ctx)
            else:
                data = await plugins.on_backend_packet(data, ctx)
            transferred += len(data)
            writer.write(data)
            if writer.transport.get_write_buffer_size() >= WRITE_HIGH_WATER:
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


async def _kill_poller(
    check_fn: Callable[[], bool],
    kill_event: asyncio.Event,
    interval: float = KILL_CHECK_INTERVAL,
) -> None:
    """Periodically run a sync Redis check in a thread, set event on kill."""
    loop = asyncio.get_running_loop()
    try:
        while not kill_event.is_set():
            killed = await loop.run_in_executor(None, check_fn)
            if killed:
                kill_event.set()
                return
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


async def relay_bidirectional(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    backend_reader: asyncio.StreamReader,
    backend_writer: asyncio.StreamWriter,
    *,
    plugins: PluginRegistry,
    ctx: SessionContext,
    kill_checker: Callable[[], bool] | None = None,
) -> RelayResult:
    """Run two pipes and stop relay when any direction is closed."""
    logger.info("Relay starting for %s", ctx.connection_id)
    kill_event: asyncio.Event | None = None
    poller_task: asyncio.Task | None = None
    if kill_checker is not None:
        kill_event = asyncio.Event()
        poller_task = asyncio.create_task(_kill_poller(kill_checker, kill_event))

    tasks = [
        asyncio.create_task(
            _pipe(
                client_reader, backend_writer, "client->backend",
                plugins=plugins, ctx=ctx, kill_event=kill_event,
            )
        ),
        asyncio.create_task(
            _pipe(
                backend_reader, client_writer, "backend->client",
                plugins=plugins, ctx=ctx, kill_event=kill_event,
            )
        ),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

    if kill_event is not None:
        kill_event.set()
    if poller_task is not None:
        poller_task.cancel()

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
