from __future__ import annotations

import logging
import pathlib
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("rdpproxy.config")

_DB_MANAGED_KEYS = frozenset({
    "ldap", "dns", "security.token_fingerprint_enforce",
    "security.login_attempts_per_minute", "security.login_lock_seconds",
    "security.admin_groups", "proxy.public_host", "proxy.listen_port",
    "redis.web_session_ttl", "redis.web_idle_ttl", "redis.rdp_token_ttl",
})


class InstanceConfig(BaseModel):
    id: str = "node-1"
    cluster_name: str = "rdpproxy-prod"
    lan_ip: str = "0.0.0.0"


class LdapConfig(BaseModel):
    server: str
    mode: str = "plain"
    port: int = 389
    tls_verify: bool = False
    bind_dn: str
    bind_password: str
    users_dn: str
    domain: str
    user_filter: str = ""


class DatabaseConfig(BaseModel):
    url: str
    pool_size: int = 20
    max_overflow: int = 10
    echo: bool = False


class DnsConfig(BaseModel):
    servers: list[str] = Field(default_factory=list)
    timeout: float = 3.0
    cache_ttl: int = 300


class ProxyConfig(BaseModel):
    public_host: str = "rdp.example.com"
    listen_port: int = 8443
    cert_path: str = ""
    key_path: str = ""
    secure_cookies: bool = True


class PortalConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8001


class AdminConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 9090
    allowed_networks: list[str] = Field(default_factory=lambda: ["10.120.0.0/24", "127.0.0.0/8"])


class RdpRelayConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8002
    proxy_protocol: bool = True
    trusted_proxies: list[str] = Field(default_factory=lambda: ["172.16.0.0/12", "10.0.0.0/8", "192.168.0.0/16", "127.0.0.0/8"])
    max_connections: int = 500


class RedisConfig(BaseModel):
    host: str = "redis"
    port: int = 6379
    password: str = ""
    db: int = 0
    web_session_ttl: int = 28800
    web_idle_ttl: int = 1800
    rdp_token_ttl: int = 300


class SecurityConfig(BaseModel):
    encryption_key: str
    token_fingerprint_enforce: bool = True
    login_attempts_per_minute: int = 8
    login_lock_seconds: int = 120
    admin_groups: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    """Top-level validated application configuration."""

    instance: InstanceConfig = Field(default_factory=InstanceConfig)
    ldap: LdapConfig | None = None
    database: DatabaseConfig
    dns: DnsConfig = Field(default_factory=DnsConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    portal: PortalConfig = Field(default_factory=PortalConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    rdp_relay: RdpRelayConfig = Field(default_factory=RdpRelayConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    security: SecurityConfig


DEFAULT_CONFIG_PATH = "/app/config.yaml"


def _warn_deprecated_keys(data: dict[str, Any]) -> None:
    """Log deprecation warnings for settings that are now DB-managed."""
    if "ldap" in data:
        logger.info(
            "LDAP settings found in config.yaml — they will be used as initial seed "
            "but are now managed through the admin panel"
        )
    if "dns" in data:
        logger.info(
            "'dns' in config.yaml is now managed via admin panel; "
            "YAML values serve as fallback only",
        )


def load_config(path: str = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load YAML config file and return a validated AppConfig."""
    cfg_path = pathlib.Path(path)
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping at top level")
    _warn_deprecated_keys(data)
    return AppConfig(**data)
