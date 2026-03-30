"""MCS Connect-Initial patching: fix serverSelectedProtocol for SSL<->HYBRID bridge."""

from __future__ import annotations

import logging
import struct

from rdp.constants import PROTOCOL_SSL, TS_UD_CS_CORE, TS_UD_SC_CORE

logger = logging.getLogger("rdpproxy.mcs")


def _patch_cs_core_server_selected_protocol(
    packet: bytearray, core_payload_off: int, core_block_len: int,
) -> int | None:
    """Patch serverSelectedProtocol in TS_UD_CS_CORE. Returns patched offset or None."""
    core_payload_end = core_payload_off + max(core_block_len - 4, 0)
    if core_payload_end > len(packet):
        return None
    pos = core_payload_off + 128
    if pos > core_payload_end:
        return None
    for size in (2, 2, 4, 2, 2, 2, 64, 1, 1):
        if pos + size > core_payload_end:
            return None
        pos += size
    if pos + 4 > core_payload_end:
        return None
    current = struct.unpack_from("<I", packet, pos)[0]
    if current == 0x00000001:
        struct.pack_into("<I", packet, pos, 0x00000002)
    return pos


def patch_mcs_client(data: bytes) -> bytes:
    """Patch client MCS ConnectInitial to match backend HYBRID negotiation."""
    packet = bytearray(data)
    for i in range(len(packet) - 3):
        block_type = struct.unpack_from("<H", packet, i)[0]
        if block_type != TS_UD_CS_CORE:
            continue
        block_len = struct.unpack_from("<H", packet, i + 2)[0]
        if block_len < 132 or i + block_len > len(packet):
            continue
        patched_off = _patch_cs_core_server_selected_protocol(packet, i + 4, block_len)
        if patched_off is None:
            continue
        logger.info("Patched MCS serverSelectedProtocol SSL->HYBRID at byte %d", patched_off)
        return bytes(packet)
    logger.info("MCS protocol patch not applied (valid TS_UD_CS_CORE block not found)")
    return bytes(packet)


def patch_mcs_server(data: bytes, *, client_requested_protocols: int | None = None) -> bytes:
    """Patch server GCC SC_CORE.clientRequestedProtocols to match the original client value."""
    packet = bytearray(data)
    for i in range(len(packet) - 3):
        block_type = struct.unpack_from("<H", packet, i)[0]
        if block_type != TS_UD_SC_CORE:
            continue
        block_len = struct.unpack_from("<H", packet, i + 2)[0]
        if block_len < 12 or i + block_len > len(packet):
            continue
        off = i + 8
        current = struct.unpack_from("<I", packet, off)[0]
        target = client_requested_protocols if client_requested_protocols is not None else PROTOCOL_SSL
        if current != target:
            struct.pack_into("<I", packet, off, target)
            logger.info("Patched MCS server clientRequestedProtocols 0x%08x->0x%08x at byte %d", current, target, off)
        return bytes(packet)
    logger.info("MCS server patch not applied (TS_UD_SC_CORE not found)")
    return bytes(packet)
