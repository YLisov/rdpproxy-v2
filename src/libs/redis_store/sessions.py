from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from hashlib import sha256

import redis as redis_lib

from config.loader import RedisConfig, SecurityConfig
from redis_store import keys
from redis_store.encryption import AESEncryptor


@dataclass
class SessionData:
    token: str
    username: str
    target_host: str
    target_port: int
    password: str
    fingerprint: str | None = None
    server_id: str | None = None
    server_display: str | None = None


@dataclass
class WebSessionData:
    session_id: str
    username: str
    groups: list[str]
    group_guids: list[str]
    password: str


@dataclass
class AdminWebSessionData:
    session_id: str
    admin_user_id: str
    username: str
    must_change_password: bool
    allowed_ips: list[str] | None = None


class SessionStore:
    """Manages web, RDP and admin sessions in Redis with AES-256-GCM encryption."""

    def __init__(self, client: redis_lib.Redis, redis_cfg: RedisConfig, security_cfg: SecurityConfig) -> None:
        self.client = client
        self.web_ttl = redis_cfg.web_session_ttl
        self.rdp_token_ttl = redis_cfg.rdp_token_ttl
        self.web_idle_ttl = redis_cfg.web_idle_ttl
        self._enc = AESEncryptor(security_cfg.encryption_key)

    def _password_aad(self, prefix: str, identifier: str, username: str) -> bytes:
        return f"{prefix}:{identifier}:{username}".encode("utf-8")

    @staticmethod
    def _fingerprint_digest(fingerprint: str) -> str:
        return sha256(fingerprint.encode("utf-8")).hexdigest()

    # ── RDP token sessions ──

    def create_session(
        self, username: str, password: str, target_host: str, target_port: int,
        server_id: str | None = None, server_display: str | None = None,
    ) -> str:
        token = secrets.token_urlsafe(32)
        key = keys.TOKEN.format(token=token)
        aad = self._password_aad("rdp:token", token, username)
        payload = {
            "username": username,
            "password_enc": self._enc.encrypt(password, aad=aad),
            "target_host": target_host,
            "target_port": int(target_port),
            "fingerprint": None,
            "server_id": server_id,
            "server_display": server_display,
        }
        self.client.setex(key, self.rdp_token_ttl, json.dumps(payload))
        return token

    def get_session(self, token: str) -> SessionData | None:
        key = keys.TOKEN.format(token=token)
        raw = self.client.get(key)
        if not raw:
            return None
        payload = json.loads(raw)
        aad = self._password_aad("rdp:token", token, payload["username"])
        return SessionData(
            token=token,
            username=payload["username"],
            target_host=payload["target_host"],
            target_port=int(payload["target_port"]),
            password=self._enc.decrypt(payload["password_enc"], aad=aad),
            fingerprint=payload.get("fingerprint"),
            server_id=payload.get("server_id"),
            server_display=payload.get("server_display"),
        )

    def set_token_fingerprint(self, token: str, fingerprint: str) -> bool:
        key = keys.TOKEN.format(token=token)
        with self.client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    raw = pipe.get(key)
                    if not raw:
                        return False
                    payload = json.loads(raw)
                    payload["fingerprint"] = self._fingerprint_digest(fingerprint)
                    ttl = pipe.ttl(key)
                    if ttl <= 0:
                        return False
                    pipe.multi()
                    pipe.setex(key, ttl, json.dumps(payload))
                    pipe.execute()
                    return True
                except redis_lib.WatchError:
                    continue

    def token_fingerprint_matches(self, token: str, fingerprint: str) -> bool:
        raw = self.client.get(keys.TOKEN.format(token=token))
        if not raw:
            return False
        payload = json.loads(raw)
        expected = payload.get("fingerprint")
        if not expected:
            return False
        return expected == self._fingerprint_digest(fingerprint)

    def delete_session(self, token: str) -> None:
        self.client.delete(keys.TOKEN.format(token=token))

    # ── Web sessions ──

    def create_web_session(
        self, username: str, password: str, groups: list[str], group_guids: list[str], browser_fingerprint: str,
    ) -> str:
        session_id = secrets.token_urlsafe(32)
        key = keys.WEB_SESSION.format(session_id=session_id)
        aad = self._password_aad("rdp:web", session_id, username)
        now = int(time.time())
        payload = {
            "username": username,
            "password_enc": self._enc.encrypt(password, aad=aad),
            "groups": groups,
            "group_guids": group_guids,
            "browser_fingerprint": self._fingerprint_digest(browser_fingerprint),
            "last_seen_ts": now,
        }
        self.client.setex(key, self.web_ttl, json.dumps(payload))
        return session_id

    def get_web_session(self, session_id: str, browser_fingerprint: str) -> WebSessionData | None:
        key = keys.WEB_SESSION.format(session_id=session_id)
        with self.client.pipeline() as pipe:
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                if not raw:
                    return None
                payload = json.loads(raw)
                expected_fp = payload.get("browser_fingerprint")
                if expected_fp and expected_fp != self._fingerprint_digest(browser_fingerprint):
                    pipe.multi()
                    pipe.delete(key)
                    pipe.execute()
                    return None
                now = int(time.time())
                last_seen_ts = int(payload.get("last_seen_ts", now))
                if now - last_seen_ts > self.web_idle_ttl:
                    pipe.multi()
                    pipe.delete(key)
                    pipe.execute()
                    return None
                payload["last_seen_ts"] = now
                ttl = pipe.ttl(key)
                if ttl > 0:
                    pipe.multi()
                    pipe.setex(key, ttl, json.dumps(payload))
                    pipe.execute()
            except redis_lib.WatchError:
                pass
        aad = self._password_aad("rdp:web", session_id, payload["username"])
        return WebSessionData(
            session_id=session_id,
            username=payload["username"],
            groups=[str(v) for v in payload.get("groups", [])],
            group_guids=[str(v) for v in payload.get("group_guids", [])],
            password=self._enc.decrypt(payload["password_enc"], aad=aad),
        )

    def delete_web_session(self, session_id: str) -> None:
        self.client.delete(keys.WEB_SESSION.format(session_id=session_id))

    # ── Admin web sessions ──

    def create_admin_web_session(
        self, *, admin_user_id: str, username: str, must_change_password: bool,
        browser_fingerprint: str, allowed_ips: list[str] | None = None,
    ) -> str:
        session_id = secrets.token_urlsafe(32)
        key = keys.ADMIN_WEB_SESSION.format(session_id=session_id)
        now = int(time.time())
        payload = {
            "admin_user_id": admin_user_id,
            "username": username,
            "must_change_password": bool(must_change_password),
            "browser_fingerprint": self._fingerprint_digest(browser_fingerprint),
            "last_seen_ts": now,
            "allowed_ips": allowed_ips or [],
        }
        self.client.setex(key, self.web_ttl, json.dumps(payload))
        return session_id

    def get_admin_web_session(self, session_id: str, browser_fingerprint: str) -> AdminWebSessionData | None:
        key = keys.ADMIN_WEB_SESSION.format(session_id=session_id)
        with self.client.pipeline() as pipe:
            try:
                pipe.watch(key)
                raw = pipe.get(key)
                if not raw:
                    return None
                payload = json.loads(raw)
                expected_fp = payload.get("browser_fingerprint")
                if expected_fp and expected_fp != self._fingerprint_digest(browser_fingerprint):
                    pipe.multi()
                    pipe.delete(key)
                    pipe.execute()
                    return None
                now = int(time.time())
                last_seen_ts = int(payload.get("last_seen_ts", now))
                if now - last_seen_ts > self.web_idle_ttl:
                    pipe.multi()
                    pipe.delete(key)
                    pipe.execute()
                    return None
                payload["last_seen_ts"] = now
                ttl = pipe.ttl(key)
                if ttl > 0:
                    pipe.multi()
                    pipe.setex(key, ttl, json.dumps(payload))
                    pipe.execute()
            except redis_lib.WatchError:
                pass
        return AdminWebSessionData(
            session_id=session_id,
            admin_user_id=str(payload["admin_user_id"]),
            username=str(payload["username"]),
            must_change_password=bool(payload.get("must_change_password")),
            allowed_ips=payload.get("allowed_ips") or [],
        )

    def update_admin_must_change(self, session_id: str, must_change_password: bool) -> None:
        key = keys.ADMIN_WEB_SESSION.format(session_id=session_id)
        raw = self.client.get(key)
        if not raw:
            return
        payload = json.loads(raw)
        payload["must_change_password"] = bool(must_change_password)
        ttl = self.client.ttl(key)
        if ttl > 0:
            self.client.setex(key, ttl, json.dumps(payload))

    def delete_admin_web_session(self, session_id: str) -> None:
        self.client.delete(keys.ADMIN_WEB_SESSION.format(session_id=session_id))
