"""CSRF token generation and validation helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time


def generate_csrf_token(session_id: str, secret: str, ttl: int = 3600) -> str:
    """Generate time-limited CSRF token bound to a session."""
    ts = str(int(time.time()))
    nonce = secrets.token_hex(8)
    payload = f"{session_id}:{ts}:{nonce}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def validate_csrf_token(token: str, session_id: str, secret: str, ttl: int = 3600) -> bool:
    parts = token.split(":")
    if len(parts) != 4:
        return False
    stored_session, ts_str, nonce, sig = parts
    if stored_session != session_id:
        return False
    try:
        ts = int(ts_str)
    except ValueError:
        return False
    if abs(time.time() - ts) > ttl:
        return False
    payload = f"{stored_session}:{ts_str}:{nonce}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)
