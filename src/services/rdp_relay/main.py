"""RDP Relay service entry point — asyncio TCP server."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from common.dns_resolver import DnsResolver
from common.logging import setup_logging
from config.loader import load_config
from db.engine import build_session_factory
from redis_store.active_tracker import ConnectionTracker
from redis_store.client import create_redis_client
from redis_store.sessions import SessionStore
from services.rdp_relay.handler import RdpConnectionHandler
from services.rdp_relay.plugins.mcs_patch import McsPatchPlugin
from services.rdp_relay.plugins.registry import PluginRegistry
from services.rdp_relay.plugins.session_monitor import SessionMonitorPlugin

logger = logging.getLogger("rdpproxy.relay")


async def run_server() -> None:
    setup_logging()
    config = load_config()
    logger.info("RDP Relay starting on %s:%d", config.rdp_relay.host, config.rdp_relay.port)

    redis_client = create_redis_client(config.redis)
    session_store = SessionStore(redis_client, config.redis, config.security)
    db_factory = build_session_factory(config.database)
    dns_resolver = DnsResolver(config.dns)
    tracker = ConnectionTracker(
        db_sessionmaker=db_factory,
        redis_client=redis_client,
        instance_id=config.instance.id,
    )
    stale_db, stale_redis = await tracker.reconcile_stale_active_on_startup()
    if stale_db or stale_redis:
        logger.warning(
            "Cleaned stale active sessions on startup: db=%d redis=%d",
            stale_db,
            stale_redis,
        )

    plugins = PluginRegistry([
        McsPatchPlugin(),
        SessionMonitorPlugin(),
    ])

    handler = RdpConnectionHandler(
        config=config,
        session_store=session_store,
        tracker=tracker,
        dns_resolver=dns_resolver,
        plugin_registry=plugins,
    )

    server = await asyncio.start_server(
        handler,
        host=config.rdp_relay.host,
        port=config.rdp_relay.port,
    )
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    logger.info("RDP Relay listening on %s", addrs)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()
    logger.info("Shutting down RDP Relay…")
    server.close()
    await server.wait_closed()
    redis_client.close()
    logger.info("RDP Relay stopped")


def main() -> None:
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
