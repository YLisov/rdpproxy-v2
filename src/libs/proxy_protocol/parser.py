"""Proxy Protocol v1/v2 parser for reading real client IP from HAProxy."""

from __future__ import annotations

import struct
from dataclasses import dataclass

PP_V2_SIGNATURE = b"\r\n\r\n\x00\r\nQUIT\n"
PP_V1_PREFIX = b"PROXY "


@dataclass
class ProxyInfo:
    src_addr: str
    src_port: int
    dst_addr: str
    dst_port: int
    version: int


async def read_proxy_protocol(reader) -> ProxyInfo:
    """Read Proxy Protocol header (v1 or v2) from an asyncio StreamReader."""
    peeked = await reader.readexactly(13)

    if peeked[:12] == PP_V2_SIGNATURE:
        return await _parse_v2(reader, peeked)
    if peeked[:6] == PP_V1_PREFIX:
        return await _parse_v1(reader, peeked)
    raise ValueError(f"Not a Proxy Protocol header (first bytes: {peeked[:6].hex()})")


async def _parse_v2(reader, initial: bytes) -> ProxyInfo:
    """Parse PP v2 binary header."""
    header = initial + await reader.readexactly(3)
    ver_cmd = header[12]
    family = header[13]
    addr_len = struct.unpack("!H", header[14:16])[0]
    addr_data = await reader.readexactly(addr_len) if addr_len > 0 else b""
    ver = (ver_cmd >> 4) & 0x0F
    cmd = ver_cmd & 0x0F
    if ver != 2:
        raise ValueError(f"PP v2: unexpected version {ver}")
    if cmd == 0:
        return ProxyInfo(src_addr="local", src_port=0, dst_addr="local", dst_port=0, version=2)
    af = (family >> 4) & 0x0F
    proto = family & 0x0F
    if af == 1:
        if len(addr_data) < 12:
            raise ValueError("PP v2: AF_INET address too short")
        src_ip = ".".join(str(b) for b in addr_data[0:4])
        dst_ip = ".".join(str(b) for b in addr_data[4:8])
        src_port, dst_port = struct.unpack("!HH", addr_data[8:12])
        return ProxyInfo(src_addr=src_ip, src_port=src_port, dst_addr=dst_ip, dst_port=dst_port, version=2)
    if af == 2:
        if len(addr_data) < 36:
            raise ValueError("PP v2: AF_INET6 address too short")
        import ipaddress
        src_ip = str(ipaddress.IPv6Address(addr_data[0:16]))
        dst_ip = str(ipaddress.IPv6Address(addr_data[16:32]))
        src_port, dst_port = struct.unpack("!HH", addr_data[32:36])
        return ProxyInfo(src_addr=src_ip, src_port=src_port, dst_addr=dst_ip, dst_port=dst_port, version=2)
    raise ValueError(f"PP v2: unsupported address family {af}")


async def _parse_v1(reader, initial: bytes) -> ProxyInfo:
    """Parse PP v1 text header (PROXY TCP4/TCP6 src dst sport dport\\r\\n)."""
    buf = initial
    while b"\r\n" not in buf:
        chunk = await reader.readexactly(1)
        buf += chunk
        if len(buf) > 512:
            raise ValueError("PP v1: header too long")
    line_end = buf.index(b"\r\n")
    line = buf[:line_end].decode("ascii")
    parts = line.split()
    if len(parts) < 6:
        raise ValueError(f"PP v1: not enough fields: {line}")
    return ProxyInfo(
        src_addr=parts[2], src_port=int(parts[4]),
        dst_addr=parts[3], dst_port=int(parts[5]),
        version=1,
    )
