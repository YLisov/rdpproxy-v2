"""Async DNS resolver with in-memory caching."""

from __future__ import annotations

import asyncio
import ipaddress
import time
from dataclasses import dataclass

import dns.asyncresolver

from config.loader import DnsConfig


@dataclass
class _CacheRecord:
    ip: str
    ts: float


class DnsResolver:
    def __init__(self, cfg: DnsConfig) -> None:
        self.timeout = cfg.timeout
        self.cache_ttl = cfg.cache_ttl
        self._resolver = dns.asyncresolver.Resolver()
        if cfg.servers:
            self._resolver.nameservers = list(cfg.servers)
        self._resolver.lifetime = self.timeout
        self._resolver.timeout = self.timeout
        self._cache: dict[str, _CacheRecord] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _is_ip(value: str) -> bool:
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False

    async def resolve(self, host: str) -> str:
        h = (host or "").strip()
        if not h:
            raise ValueError("host is required")
        if self._is_ip(h):
            return h
        now = time.time()
        async with self._lock:
            item = self._cache.get(h)
            if item and (now - item.ts) <= self.cache_ttl:
                return item.ip
        answers = await self._resolver.resolve(h, "A")
        ip = str(answers[0])
        async with self._lock:
            self._cache[h] = _CacheRecord(ip=ip, ts=now)
        return ip
