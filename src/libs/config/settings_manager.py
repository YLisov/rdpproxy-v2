"""Centralized settings manager: DB-backed with in-memory cache and hot-reload hooks."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Awaitable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config.loader import AppConfig, DnsConfig, LdapConfig
from db.models.settings import PortalSetting
from redis_store.encryption import AESEncryptor

logger = logging.getLogger("rdpproxy.settings")

MANAGED_KEYS = ("ldap", "dns", "proxy", "security", "redis_ttl", "portal")

_SECRET_AAD = b"portal_settings:ldap:bind_password"


class SettingsManager:
    """Loads settings from ``portal_settings`` table with fallback to YAML config.

    On first startup with empty DB the manager seeds values from the YAML
    ``AppConfig`` so existing deployments migrate transparently.
    """

    def __init__(
        self,
        db_sessionmaker: async_sessionmaker[AsyncSession],
        base_config: AppConfig,
        encryption_key: str,
    ) -> None:
        self._db = db_sessionmaker
        self._base = base_config
        self._enc = AESEncryptor(encryption_key)
        self._cache: dict[str, dict[str, Any]] = {}
        self._loaded_at: float = 0
        self._ttl: float = 30.0
        self._lock = asyncio.Lock()
        self._hooks: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = {}
        self._seeded = False

    # ── public API ──

    async def load(self) -> None:
        """Read all portal_settings rows into the cache."""
        async with self._lock:
            async with self._db() as session:
                rows = await session.execute(sa.select(PortalSetting))
                fresh: dict[str, dict[str, Any]] = {}
                for r in rows.scalars().all():
                    if isinstance(r.value, dict):
                        fresh[r.key] = dict(r.value)
                self._cache = fresh
                self._loaded_at = time.monotonic()

            if not self._seeded:
                await self._seed_from_yaml()
                self._seeded = True

    async def get(self, key: str) -> dict[str, Any]:
        """Return setting by key; auto-refresh if stale; fallback to YAML."""
        if time.monotonic() - self._loaded_at > self._ttl:
            await self.load()
        raw = self._cache.get(key)
        if raw is not None:
            if key == "ldap" and "bind_password_enc" in raw:
                raw = dict(raw)
                raw["bind_password"] = self._decrypt_password(raw.pop("bind_password_enc"))
            return raw
        return self._get_fallback(key) or {}

    async def save(self, key: str, value: dict[str, Any], *, publish_redis: Any = None) -> None:
        """Persist to DB, update cache, fire hooks, optionally publish change."""
        store_value = dict(value)
        if key == "ldap" and "bind_password" in store_value:
            pwd = store_value.pop("bind_password")
            if pwd:
                store_value["bind_password_enc"] = self._encrypt_password(pwd)

        async with self._db() as session:
            row = await session.get(PortalSetting, key)
            if row is None:
                session.add(PortalSetting(key=key, value=store_value))
            else:
                if isinstance(row.value, dict):
                    merged = {**dict(row.value), **store_value}
                else:
                    merged = store_value
                row.value = merged
            await session.commit()

        if key in self._cache and isinstance(self._cache[key], dict):
            self._cache[key] = {**self._cache[key], **store_value}
        else:
            self._cache[key] = store_value
        self._loaded_at = time.monotonic()

        await self._run_hooks(key)

        if publish_redis is not None:
            try:
                from redis_store.keys import SETTINGS_CHANGED_CHANNEL
                publish_redis.publish(SETTINGS_CHANGED_CHANNEL, key)
            except Exception:
                logger.warning("Failed to publish settings change to Redis")

    def on_change(self, key: str, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Register an async callback invoked when *key* is saved."""
        self._hooks.setdefault(key, []).append(callback)

    # ── typed accessors ──

    @property
    def ldap(self) -> LdapConfig | None:
        raw = self._cache.get("ldap")
        if raw is None:
            if self._base.ldap is not None:
                return self._base.ldap
            return None
        try:
            resolved = dict(raw)
            if "bind_password_enc" in resolved:
                resolved["bind_password"] = self._decrypt_password(resolved.pop("bind_password_enc"))
            resolved.pop("bind_password_enc", None)
            if "bind_password" not in resolved or not resolved["bind_password"]:
                if self._base.ldap is not None:
                    resolved.setdefault("bind_password", self._base.ldap.bind_password)
            return LdapConfig(**resolved)
        except Exception:
            logger.exception("Failed to parse LDAP settings from DB, falling back to YAML")
            return self._base.ldap

    @property
    def dns(self) -> DnsConfig:
        raw = self._cache.get("dns")
        if raw is None:
            return self._base.dns
        try:
            return DnsConfig(**raw)
        except Exception:
            return self._base.dns

    @property
    def proxy_params(self) -> dict[str, Any]:
        raw = self._cache.get("proxy")
        if raw is None:
            return {"public_host": self._base.proxy.public_host, "listen_port": self._base.proxy.listen_port}
        return {
            "public_host": raw.get("public_host", self._base.proxy.public_host),
            "listen_port": raw.get("listen_port", self._base.proxy.listen_port),
        }

    @property
    def security_params(self) -> dict[str, Any]:
        defaults = {
            "token_fingerprint_enforce": self._base.security.token_fingerprint_enforce,
            "login_attempts_per_minute": self._base.security.login_attempts_per_minute,
            "login_lock_seconds": self._base.security.login_lock_seconds,
            "admin_groups": list(self._base.security.admin_groups),
            "delete_token_on_disconnect": self._base.security.delete_token_on_disconnect,
        }
        raw = self._cache.get("security")
        if raw is None:
            return defaults
        defaults.update({k: v for k, v in raw.items() if k != "encryption_key"})
        return defaults

    @property
    def redis_ttl(self) -> dict[str, int]:
        defaults = {
            "web_session_ttl": self._base.redis.web_session_ttl,
            "web_idle_ttl": self._base.redis.web_idle_ttl,
            "rdp_token_ttl": self._base.redis.rdp_token_ttl,
        }
        raw = self._cache.get("redis_ttl")
        if raw is None:
            return defaults
        for k in defaults:
            if k in raw and isinstance(raw[k], (int, float)):
                defaults[k] = int(raw[k])
        return defaults

    def get_all_for_ui(self) -> dict[str, Any]:
        """Return all settings for the admin UI, with secrets stripped."""
        out: dict[str, Any] = {}
        ldap = self.ldap
        if ldap:
            d = ldap.model_dump()
            d.pop("bind_password", None)
            out["ldap"] = d
        out["dns"] = self.dns.model_dump()
        out["proxy"] = self.proxy_params
        out["security"] = self.security_params
        out["redis_ttl"] = self.redis_ttl
        raw_portal = self._cache.get("portal")
        out["portal"] = raw_portal if raw_portal else {"name": "DC319"}
        return out

    # ── internal ──

    def _encrypt_password(self, plaintext: str) -> str:
        return self._enc.encrypt(plaintext, aad=_SECRET_AAD)

    def _decrypt_password(self, blob: str) -> str:
        return self._enc.decrypt(blob, aad=_SECRET_AAD)

    def _get_fallback(self, key: str) -> dict[str, Any] | None:
        if key == "ldap" and self._base.ldap is not None:
            return self._base.ldap.model_dump()
        if key == "dns":
            return self._base.dns.model_dump()
        if key == "proxy":
            return {"public_host": self._base.proxy.public_host, "listen_port": self._base.proxy.listen_port}
        if key == "security":
            d = self._base.security.model_dump()
            d.pop("encryption_key", None)
            return d
        if key == "redis_ttl":
            return {
                "web_session_ttl": self._base.redis.web_session_ttl,
                "web_idle_ttl": self._base.redis.web_idle_ttl,
                "rdp_token_ttl": self._base.redis.rdp_token_ttl,
            }
        if key == "portal":
            return {"name": "DC319"}
        return None

    async def _seed_from_yaml(self) -> None:
        """On first run, populate DB with defaults / YAML values.

        Also patches up existing DB entries that are missing subkeys
        (e.g. ``redis_ttl`` saved with only ``rdp_token_ttl``).
        """
        for key in MANAGED_KEYS:
            fallback = self._get_fallback(key)
            if not fallback:
                continue

            cached = self._cache.get(key)
            if cached is None:
                store_value = dict(fallback)
                if key == "ldap" and "bind_password" in store_value:
                    pwd = store_value.pop("bind_password")
                    if pwd:
                        store_value["bind_password_enc"] = self._encrypt_password(pwd)
                try:
                    async with self._db() as session:
                        existing = await session.get(PortalSetting, key)
                        if existing is None:
                            session.add(PortalSetting(key=key, value=store_value))
                            await session.commit()
                            self._cache[key] = store_value
                            logger.info("Seeded '%s' settings into database", key)
                except Exception:
                    logger.warning("Failed to seed '%s'", key, exc_info=True)
            else:
                patch_source = dict(fallback)
                if key == "ldap":
                    patch_source.pop("bind_password", None)
                missing = {k: v for k, v in patch_source.items() if k not in cached}
                if not missing:
                    continue
                try:
                    async with self._db() as session:
                        row = await session.get(PortalSetting, key)
                        if row is not None and isinstance(row.value, dict):
                            patched = {**dict(row.value), **missing}
                            row.value = patched
                            await session.commit()
                            self._cache[key] = patched
                            logger.info("Patched missing subkeys for '%s': %s", key, list(missing))
                except Exception:
                    logger.warning("Failed to patch '%s'", key, exc_info=True)

    async def _run_hooks(self, key: str) -> None:
        data = await self.get(key)
        for cb in self._hooks.get(key, []):
            try:
                await cb(data)
            except Exception:
                logger.exception("Settings hook failed for key '%s'", key)
