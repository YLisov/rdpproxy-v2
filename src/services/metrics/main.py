"""Metrics collector service entry point."""

from __future__ import annotations

import asyncio
import logging
import signal

from common.logging import setup_logging
from config.loader import load_config
from db.engine import build_session_factory
from redis_store.client import create_redis_client
from services.metrics.collector import MetricsCollector

logger = logging.getLogger("rdpproxy.metrics")


async def run() -> None:
    setup_logging()
    config = load_config()
    logger.info("Metrics service starting (instance=%s)", config.instance.id)

    redis_client = create_redis_client(config.redis)
    db_factory = build_session_factory(config.database)

    collector = MetricsCollector(
        redis_client=redis_client,
        db_sessionmaker=db_factory,
        instance_id=config.instance.id,
        lan_ip=config.instance.lan_ip,
        interval_sec=10,
    )
    collector.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    logger.info("Shutting down metrics collector…")
    await collector.stop()
    redis_client.close()
    logger.info("Metrics service stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
