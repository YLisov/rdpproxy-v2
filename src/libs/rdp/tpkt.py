"""TPKT frame helpers (RFC 1006)."""

from __future__ import annotations

import asyncio
import struct

from rdp.constants import TPKT_VERSION


def build_tpkt(payload: bytes) -> bytes:
    return bytes([TPKT_VERSION, 0]) + struct.pack(">H", len(payload) + 4) + payload


async def read_tpkt(reader: asyncio.StreamReader, initial_data: bytes = b"") -> bytes:
    """Read one TPKT frame and return its payload (without the 4-byte header)."""
    header = initial_data
    if len(header) < 4:
        header += await reader.readexactly(4 - len(header))
    if header[0] != TPKT_VERSION:
        raise ValueError("Invalid TPKT version")
    total_len = struct.unpack(">H", header[2:4])[0]
    return await reader.readexactly(total_len - 4)
