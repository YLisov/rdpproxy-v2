from __future__ import annotations

import redis

from config.loader import RedisConfig


def create_redis_client(cfg: RedisConfig) -> redis.Redis:
    """Create a synchronous Redis client from config."""
    return redis.Redis(
        host=cfg.host,
        port=cfg.port,
        db=cfg.db,
        password=cfg.password or None,
        decode_responses=True,
    )
