"""X.224 Connection Request / Confirm builders and helpers."""

from __future__ import annotations

import hashlib
import re
import struct

from rdp.constants import PROTOCOL_SSL, REQUESTED_PROTOCOLS_HYBRID
from rdp.tpkt import build_tpkt


def build_x224_cr(requested_protocols: int = REQUESTED_PROTOCOLS_HYBRID) -> bytes:
    """Build X.224 Connection Request for backend with given protocol flags."""
    x224 = b"\x0e\xe0\x00\x00\x00\x00\x00"
    rdp_neg_req = b"\x01\x00\x08\x00" + struct.pack("<I", requested_protocols)
    return build_tpkt(x224 + rdp_neg_req)


def build_x224_cc_ssl() -> bytes:
    """Build X.224 Connection Confirm selecting TLS (PROTOCOL_SSL)."""
    x224_cc = b"\x0e\xd0\x00\x00\x12\x34\x00"
    rdp_neg_rsp = b"\x02\x00\x08\x00" + struct.pack("<I", PROTOCOL_SSL)
    return build_tpkt(x224_cc + rdp_neg_rsp)


def extract_cookie_token(x224_payload: bytes) -> str:
    """Extract RDP routing token (msts= / mstshash=) from X.224 CR payload."""
    markers = (b"Cookie: msts=", b"cookie: msts=", b"Cookie: mstshash=", b"cookie: mstshash=")
    for marker in markers:
        start = x224_payload.find(marker)
        if start == -1:
            continue
        start += len(marker)
        end = x224_payload.find(b"\r\n", start)
        if end == -1:
            end = len(x224_payload)
        token = x224_payload[start:end].decode("utf-8", errors="ignore").strip()
        if token:
            return token
    candidates = re.findall(rb"[A-Za-z0-9_-]{20,}", x224_payload)
    for candidate in candidates:
        token = candidate.decode("utf-8", errors="ignore")
        if "-" in token or "_" in token:
            return token
        if len(token) >= 32 and any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
            return token
    raise ValueError("loadbalanceinfo token not found in initial X.224 payload")


def extract_rdp_client_hint(x224_payload: bytes) -> str:
    markers = (b"Cookie: mstshash=", b"cookie: mstshash=")
    for marker in markers:
        start = x224_payload.find(marker)
        if start == -1:
            continue
        start += len(marker)
        end = x224_payload.find(b"\r\n", start)
        if end == -1:
            end = len(x224_payload)
        value = x224_payload[start:end].decode("utf-8", errors="ignore").strip()
        if value:
            return value
    return ""


def extract_requested_protocols(x224_payload: bytes) -> int:
    """Extract requestedProtocols from the RDP Negotiation Request in X.224 CR."""
    marker = x224_payload.find(b"\x01\x00\x08\x00")
    if marker != -1 and marker + 8 <= len(x224_payload):
        return struct.unpack_from("<I", x224_payload, marker + 4)[0]
    return REQUESTED_PROTOCOLS_HYBRID


def build_rdp_client_fingerprint(x224_payload: bytes, token: str) -> str:
    hint = extract_rdp_client_hint(x224_payload)
    token_bytes = token.encode("utf-8")
    redacted = x224_payload.replace(token_bytes, b"<TOKEN>")
    digest = hashlib.sha256(redacted).hexdigest()
    return f"{hint}|{digest}"
