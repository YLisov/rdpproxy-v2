"""Connection quality monitoring plugin: TCP_INFO-based metrics for active RDP sessions."""

from __future__ import annotations

import asyncio
import ctypes
import json
import logging
import socket
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

import redis as redis_lib

from services.rdp_relay.plugins.base import RdpPlugin, SessionContext

logger = logging.getLogger("rdpproxy.relay.connection_quality")

TCP_INFO_OPT = 11
_WINDOW_SIZE = 20


class _TcpInfo(ctypes.Structure):
    """First 32 fields of ``struct tcp_info`` from ``<linux/tcp.h>`` (kernel 4.1+)."""

    _fields_ = [
        ("tcpi_state", ctypes.c_uint8),
        ("tcpi_ca_state", ctypes.c_uint8),
        ("tcpi_retransmits", ctypes.c_uint8),
        ("tcpi_probes", ctypes.c_uint8),
        ("tcpi_backoff", ctypes.c_uint8),
        ("tcpi_options", ctypes.c_uint8),
        ("tcpi_snd_wscale_rcv_wscale", ctypes.c_uint8),
        ("tcpi_delivery_rate_app_limited", ctypes.c_uint8),
        ("tcpi_rto", ctypes.c_uint32),
        ("tcpi_ato", ctypes.c_uint32),
        ("tcpi_snd_mss", ctypes.c_uint32),
        ("tcpi_rcv_mss", ctypes.c_uint32),
        ("tcpi_unacked", ctypes.c_uint32),
        ("tcpi_sacked", ctypes.c_uint32),
        ("tcpi_lost", ctypes.c_uint32),
        ("tcpi_retrans", ctypes.c_uint32),
        ("tcpi_fackets", ctypes.c_uint32),
        # Times
        ("tcpi_last_data_sent", ctypes.c_uint32),
        ("tcpi_last_ack_sent", ctypes.c_uint32),
        ("tcpi_last_data_recv", ctypes.c_uint32),
        ("tcpi_last_ack_recv", ctypes.c_uint32),
        # Metrics
        ("tcpi_pmtu", ctypes.c_uint32),
        ("tcpi_rcv_ssthresh", ctypes.c_uint32),
        ("tcpi_rtt", ctypes.c_uint32),
        ("tcpi_rttvar", ctypes.c_uint32),
        ("tcpi_snd_ssthresh", ctypes.c_uint32),
        ("tcpi_snd_cwnd", ctypes.c_uint32),
        ("tcpi_advmss", ctypes.c_uint32),
        ("tcpi_reordering", ctypes.c_uint32),
        ("tcpi_rcv_rtt", ctypes.c_uint32),
        ("tcpi_rcv_space", ctypes.c_uint32),
        ("tcpi_total_retrans", ctypes.c_uint32),
    ]


@dataclass
class QualitySnapshot:
    rtt_ms: float
    rtt_var_ms: float
    jitter_ms: float
    retransmits: int
    total_retrans: int
    lost: int
    cwnd: int
    rating: str


def _read_tcp_info(sock: socket.socket) -> _TcpInfo | None:
    try:
        buf = sock.getsockopt(socket.IPPROTO_TCP, TCP_INFO_OPT, ctypes.sizeof(_TcpInfo))
        return _TcpInfo.from_buffer_copy(buf)
    except (OSError, ValueError):
        return None


def _compute_rating(rtt_ms: float, jitter_ms: float, retrans_per_interval: int) -> str:
    if rtt_ms < 20 and jitter_ms < 5 and retrans_per_interval == 0:
        return "excellent"
    if rtt_ms < 50 and jitter_ms < 15 and retrans_per_interval < 5:
        return "good"
    if rtt_ms < 150 and jitter_ms < 40:
        return "fair"
    return "poor"


class ConnectionQualityPlugin(RdpPlugin):
    name = "connection_quality"

    def __init__(self, *, redis_client: redis_lib.Redis, instance_id: str) -> None:
        self._redis = redis_client
        self._instance_id = instance_id
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def on_session_start(self, ctx: SessionContext) -> None:
        client_sock = ctx.extra.get("client_socket")
        backend_sock = ctx.extra.get("backend_socket")
        if client_sock is None or backend_sock is None:
            logger.warning("Sockets not available in ctx.extra, quality monitoring disabled for %s", ctx.connection_id)
            return
        task = asyncio.create_task(self._monitor_loop(ctx, client_sock, backend_sock))
        self._tasks[ctx.connection_id] = task
        logger.info("Quality monitoring started for %s", ctx.connection_id)

    async def on_session_end(self, ctx: SessionContext) -> None:
        task = self._tasks.pop(ctx.connection_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.info("Quality monitoring stopped for %s", ctx.connection_id)

    async def _monitor_loop(
        self,
        ctx: SessionContext,
        client_sock: socket.socket,
        backend_sock: socket.socket,
    ) -> None:
        rtt_history: deque[float] = deque(maxlen=_WINDOW_SIZE)
        prev_total_retrans = 0
        try:
            await asyncio.sleep(2)
            while True:
                snapshot, prev_total_retrans = self._sample(
                    client_sock, backend_sock, rtt_history, prev_total_retrans,
                )
                if snapshot is not None:
                    self._publish(ctx.connection_id, snapshot)
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Quality monitor loop error for %s", ctx.connection_id)

    def _sample(
        self,
        client_sock: socket.socket,
        backend_sock: socket.socket,
        rtt_history: deque[float],
        prev_total_retrans: int,
    ) -> tuple[QualitySnapshot | None, int]:
        c_info = _read_tcp_info(client_sock)
        b_info = _read_tcp_info(backend_sock)
        if c_info is None or b_info is None:
            return None, prev_total_retrans

        rtt_us = c_info.tcpi_rtt + b_info.tcpi_rtt
        rtt_ms = rtt_us / 1000.0
        rtt_var_ms = (c_info.tcpi_rttvar + b_info.tcpi_rttvar) / 1000.0

        rtt_history.append(rtt_ms)
        jitter_ms = 0.0
        if len(rtt_history) >= 2:
            mean = sum(rtt_history) / len(rtt_history)
            jitter_ms = sum(abs(v - mean) for v in rtt_history) / len(rtt_history)

        total_retrans = c_info.tcpi_total_retrans + b_info.tcpi_total_retrans
        retrans_delta = max(0, total_retrans - prev_total_retrans)
        lost = c_info.tcpi_lost + b_info.tcpi_lost
        retransmits = c_info.tcpi_retransmits + b_info.tcpi_retransmits
        cwnd = min(c_info.tcpi_snd_cwnd, b_info.tcpi_snd_cwnd)

        rating = _compute_rating(rtt_ms, jitter_ms, retrans_delta)

        snapshot = QualitySnapshot(
            rtt_ms=round(rtt_ms, 2),
            rtt_var_ms=round(rtt_var_ms, 2),
            jitter_ms=round(jitter_ms, 2),
            retransmits=retransmits,
            total_retrans=total_retrans,
            lost=lost,
            cwnd=cwnd,
            rating=rating,
        )
        return snapshot, total_retrans

    def _publish(self, connection_id: str, snapshot: QualitySnapshot) -> None:
        key = f"rdp:active:{self._instance_id}:{connection_id}"
        try:
            raw = self._redis.get(key)
            data: dict[str, Any] = {}
            if raw and raw != b"1":
                data = json.loads(raw)
            data["connection_quality"] = snapshot.rating
            data["quality_detail"] = asdict(snapshot)
            self._redis.set(key, json.dumps(data, ensure_ascii=False), ex=24 * 3600)
        except Exception:
            logger.exception("Failed to publish quality for %s", connection_id)
