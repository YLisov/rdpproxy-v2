from __future__ import annotations

import pathlib
from typing import Any

import yaml
from pydantic import BaseModel, Field


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
    ldap: LdapConfig
    database: DatabaseConfig
    dns: DnsConfig = Field(default_factory=DnsConfig)
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    portal: PortalConfig = Field(default_factory=PortalConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    rdp_relay: RdpRelayConfig = Field(default_factory=RdpRelayConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    security: SecurityConfig


DEFAULT_CONFIG_PATH = "/app/config.yaml"


def load_config(path: str = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load YAML config file and return a validated AppConfig."""
    cfg_path = pathlib.Path(path)
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping at top level")
    return AppConfig(**data)
