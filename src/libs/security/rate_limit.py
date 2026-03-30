"""Redis-backed rate limiter for anti-bruteforce protection."""

from __future__ import annotations

import time

import redis as redis_lib

from config.loader import SecurityConfig


class RateLimiter:
    """Sliding-window rate limiter using Redis sorted sets."""

    def __init__(self, client: redis_lib.Redis, cfg: SecurityConfig) -> None:
        self.client = client
        self.max_attempts = cfg.login_attempts_per_minute
        self.lock_seconds = cfg.login_lock_seconds

    def _key(self, identifier: str) -> str:
        return f"rdp:rate:{identifier}"

    def _lock_key(self, identifier: str) -> str:
        return f"rdp:locked:{identifier}"

    def is_locked(self, identifier: str) -> bool:
        return bool(self.client.exists(self._lock_key(identifier)))

    def record_attempt(self, identifier: str) -> bool:
        """Record a login attempt. Returns True if the attempt is allowed, False if rate-limited."""
        if self.is_locked(identifier):
            return False
        now = time.time()
        key = self._key(identifier)
        window_start = now - 60
        pipe = self.client.pipeline()
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, 120)
        results = pipe.execute()
        count = results[2]
        if count > self.max_attempts:
            self.client.setex(self._lock_key(identifier), self.lock_seconds, "1")
            return False
        return True

    def reset(self, identifier: str) -> None:
        pipe = self.client.pipeline()
        pipe.delete(self._key(identifier))
        pipe.delete(self._lock_key(identifier))
        pipe.execute()
