from __future__ import annotations

import base64
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class AESEncryptor:
    """AES-256-GCM encrypt/decrypt helper for session passwords."""

    def __init__(self, key_hex: str) -> None:
        self.key = bytes.fromhex(key_hex)
        if len(self.key) != 32:
            raise ValueError("security.encryption_key must be 32 bytes (64 hex chars)")
        self._aesgcm = AESGCM(self.key)

    def encrypt(self, plaintext: str, *, aad: bytes) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, blob: str, *, aad: bytes) -> str:
        raw = base64.b64decode(blob.encode("ascii"))
        nonce, ciphertext = raw[:12], raw[12:]
        plain = self._aesgcm.decrypt(nonce, ciphertext, aad)
        return plain.decode("utf-8")
