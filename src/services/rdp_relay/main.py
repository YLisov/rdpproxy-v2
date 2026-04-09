"""RDP Relay service entry point — asyncio TCP server."""

from __future__ import annotations

import asyncio
import logging
import signal

from common.dns_resolver import DnsResolver
from common.logging import setup_logging
from config.loader import load_config
from config.settings_manager import SettingsManager
from db.engine import build_session_factory
from redis_store import keys
from redis_store.active_tracker import ConnectionTracker
from redis_store.client import create_redis_client
from redis_store.sessions import SessionStore
from services.rdp_relay.handler import RdpConnectionHandler
from services.rdp_relay.plugins.connection_quality import ConnectionQualityPlugin
from services.rdp_relay.plugins.mcs_patch import McsPatchPlugin
from services.rdp_relay.plugins.registry import PluginRegistry
from services.rdp_relay.plugins.session_monitor import SessionMonitorPlugin

logger = logging.getLogger("rdpproxy.relay")


async def _settings_listener(
    redis_client,
    settings_mgr: SettingsManager,
    handler: RdpConnectionHandler,
    session_store: SessionStore,
    session_monitor_plugin: SessionMonitorPlugin,
    conn_semaphore: asyncio.Semaphore,
    conn_limit: list[int],
) -> None:
    """Background task: listen for settings changes via Redis pub/sub."""
    try:
        pubsub = redis_client.pubsub()
        pubsub.subscribe(keys.SETTINGS_CHANGED_CHANNEL)
        while True:
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg["type"] == "message":
                await settings_mgr.load()
                dns_cfg = settings_mgr.dns
                handler.update_dns(DnsResolver(dns_cfg))
                handler.update_settings(settings_mgr)
                ttl = settings_mgr.redis_ttl
                session_store.web_ttl = ttl.get("web_session_ttl", session_store.web_ttl)
                session_store.rdp_token_ttl = ttl.get("rdp_token_ttl", session_store.rdp_token_ttl)
                session_store.web_idle_ttl = ttl.get("web_idle_ttl", session_store.web_idle_ttl)
                rp = settings_mgr.relay_params
                session_monitor_plugin.update_timeouts(
                    idle_timeout=rp.get("idle_timeout", session_monitor_plugin._idle_timeout),
                    max_session_duration=rp.get("max_session_duration", session_monitor_plugin._max_session_duration),
                )
                new_max = rp.get("max_connections", conn_limit[0])
                if new_max != conn_limit[0]:
                    diff = new_max - conn_limit[0]
                    conn_limit[0] = new_max
                    if diff > 0:
                        for _ in range(diff):
                            conn_semaphore.release()
                    logger.info("max_connections updated to %d", new_max)
                logger.info("RDP Relay reloaded settings after pub/sub notification")
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Settings listener crashed")


async def run_server() -> None:
    setup_logging()
    config = load_config()
    logger.info("RDP Relay starting on %s:%d", config.rdp_relay.host, config.rdp_relay.port)

    redis_client = create_redis_client(config.redis)
    session_store = SessionStore(redis_client, config.redis, config.security)
    db_factory = build_session_factory(config.database)

    settings_mgr = SettingsManager(db_factory, config, config.security.encryption_key)
    await settings_mgr.load()

    dns_resolver = DnsResolver(settings_mgr.dns)

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

    ttl = settings_mgr.redis_ttl
    session_store.web_ttl = ttl.get("web_session_ttl", session_store.web_ttl)
    session_store.rdp_token_ttl = ttl.get("rdp_token_ttl", session_store.rdp_token_ttl)
    session_store.web_idle_ttl = ttl.get("web_idle_ttl", session_store.web_idle_ttl)

    relay = settings_mgr.relay_params
    session_monitor = SessionMonitorPlugin(
        idle_timeout=relay.get("idle_timeout", config.rdp_relay.idle_timeout),
        max_session_duration=relay.get("max_session_duration", config.rdp_relay.max_session_duration),
    )
    plugins = PluginRegistry([
        McsPatchPlugin(),
        session_monitor,
        ConnectionQualityPlugin(redis_client=redis_client, instance_id=config.instance.id),
    ])

    handler = RdpConnectionHandler(
        config=config,
        session_store=session_store,
        tracker=tracker,
        dns_resolver=dns_resolver,
        plugin_registry=plugins,
        settings_manager=settings_mgr,
    )

    max_conn = relay.get("max_connections", config.rdp_relay.max_connections)
    conn_semaphore = asyncio.Semaphore(max_conn)
    conn_limit = [max_conn]

    async def _limited_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if conn_semaphore.locked():
            logger.warning("Max connections (%d) reached, rejecting client", conn_limit[0])
            from services.rdp_relay.tcp_utils import abort_writer
            abort_writer(writer)
            return
        async with conn_semaphore:
            await handler(reader, writer)

    server = await asyncio.start_server(
        _limited_handler,
        host=config.rdp_relay.host,
        port=config.rdp_relay.port,
    )
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    logger.info("RDP Relay listening on %s (max_connections=%d)", addrs, max_conn)

    listener_task = asyncio.create_task(
        _settings_listener(
            redis_client, settings_mgr, handler, session_store,
            session_monitor, conn_semaphore, conn_limit,
        )
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()
    logger.info("Shutting down RDP Relay…")
    listener_task.cancel()
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
