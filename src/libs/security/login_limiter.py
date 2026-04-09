"""Shared login rate-limiting logic for portal and admin authentication."""

from __future__ import annotations

import redis as redis_lib

from redis_store import keys


class LoginLimiter:
    """Rate-limiter that tracks failed login attempts per IP and username.

    Uses separate Redis key prefixes for portal vs admin to keep namespaces isolated.
    """

    def __init__(
        self,
        redis_client: redis_lib.Redis,
        *,
        fail_ip_pattern: str,
        fail_user_pattern: str,
        lock_ip_pattern: str,
        lock_user_pattern: str,
    ) -> None:
        self._rc = redis_client
        self._fail_ip = fail_ip_pattern
        self._fail_user = fail_user_pattern
        self._lock_ip = lock_ip_pattern
        self._lock_user = lock_user_pattern

    def is_locked(self, ip: str, username: str) -> bool:
        uname = username.strip().lower() or "_"
        return bool(
            self._rc.exists(self._lock_ip.format(ip=ip))
            or self._rc.exists(self._lock_user.format(username=uname))
        )

    def record_failure(self, ip: str, username: str, *, max_attempts: int, lock_seconds: int) -> None:
        uname = username.strip().lower() or "_"
        ip_key = self._fail_ip.format(ip=ip)
        user_key = self._fail_user.format(username=uname)

        ip_cnt = self._rc.incr(ip_key)
        user_cnt = self._rc.incr(user_key)
        self._rc.expire(ip_key, keys.FAIL_COUNTER_TTL)
        self._rc.expire(user_key, keys.FAIL_COUNTER_TTL)

        if ip_cnt > max_attempts:
            self._rc.setex(self._lock_ip.format(ip=ip), lock_seconds, "1")
        if user_cnt > max_attempts:
            self._rc.setex(self._lock_user.format(username=uname), lock_seconds, "1")

    def clear(self, ip: str, username: str) -> None:
        uname = username.strip().lower() or "_"
        self._rc.delete(
            self._fail_ip.format(ip=ip),
            self._fail_user.format(username=uname),
        )


def portal_limiter(redis_client: redis_lib.Redis) -> LoginLimiter:
    return LoginLimiter(
        redis_client,
        fail_ip_pattern=keys.PORTAL_FAIL_IP,
        fail_user_pattern=keys.PORTAL_FAIL_USER,
        lock_ip_pattern=keys.PORTAL_LOCK_IP,
        lock_user_pattern=keys.PORTAL_LOCK_USER,
    )


def admin_limiter(redis_client: redis_lib.Redis) -> LoginLimiter:
    return LoginLimiter(
        redis_client,
        fail_ip_pattern=keys.ADMIN_FAIL_IP,
        fail_user_pattern=keys.ADMIN_FAIL_USER,
        lock_ip_pattern=keys.ADMIN_LOCK_IP,
        lock_user_pattern=keys.ADMIN_LOCK_USER,
    )
