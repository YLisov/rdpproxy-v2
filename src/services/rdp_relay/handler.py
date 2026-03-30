"""RDP connection handler: X.224 → TLS → CredSSP → bidirectional relay.

This module orchestrates an incoming RDP connection through:
1. (Optional) Proxy Protocol v2 header parsing for real client IP
2. TPKT/X.224 Connection Request reading and routing-token extraction
3. X.224 Connection Confirm (TLS) response
4. Client-side TLS upgrade
5. CredSSP/NTLM authentication against the target RDP server
6. Plugin-enhanced bidirectional data relay
7. Connection tracking (Redis active set + PostgreSQL history)
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Any

from common.dns_resolver import DnsResolver
from config.loader import AppConfig
from proxy_protocol.parser import read_proxy_protocol
from rdp.credssp import connect_and_authenticate
from rdp.tpkt import read_tpkt
from rdp.x224 import (
    build_rdp_client_fingerprint,
    build_x224_cc_ssl,
    extract_cookie_token,
    extract_requested_protocols,
)
from redis_store.active_tracker import ConnectionTracker
from redis_store.sessions import SessionStore
from services.rdp_relay.plugins.base import SessionContext
from services.rdp_relay.plugins.registry import PluginRegistry
from services.rdp_relay.relay import RelayResult, relay_bidirectional
from services.rdp_relay.tcp_utils import abort_writer, configure_tcp_keepalive

logger = logging.getLogger("rdpproxy.relay.handler")


def _make_tls_context(cert_path: str, key_path: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
    return ctx


class RdpConnectionHandler:
    """Handles a single inbound RDP connection through the full lifecycle."""

    def __init__(
        self,
        config: AppConfig,
        session_store: SessionStore,
        tracker: ConnectionTracker,
        dns_resolver: DnsResolver,
        plugin_registry: PluginRegistry,
    ) -> None:
        self._cfg = config
        self._sessions = session_store
        self._tracker = tracker
        self._dns = dns_resolver
        self._plugins = plugin_registry

    async def __call__(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        tracked_cid: str | None = None
        client_ip = "unknown"
        try:
            client_ip = await self._resolve_client_ip(client_reader, client_writer)
            x224_request = await read_tpkt(client_reader)
            token = extract_cookie_token(x224_request)
            client_requested_protocols = extract_requested_protocols(x224_request)
            logger.info("RDP request from %s, token extracted, requestedProtocols=0x%x", client_ip, client_requested_protocols)

            session = self._sessions.get_session(token)
            if session is None:
                logger.warning("RDP token not found or expired (client=%s)", client_ip)
                abort_writer(client_writer)
                return

            if self._cfg.security.token_fingerprint_enforce:
                client_fp = build_rdp_client_fingerprint(x224_request, token)
                if session.fingerprint:
                    if not self._sessions.token_fingerprint_matches(token, client_fp):
                        logger.warning("Token fingerprint mismatch (client=%s)", client_ip)
                        abort_writer(client_writer)
                        return
                else:
                    self._sessions.set_token_fingerprint(token, client_fp)

            tracked = await self._tracker.start(
                username=session.username,
                server_id=session.server_id,
                server_display=session.server_display,
                server_address=session.target_host,
                server_port=int(session.target_port),
                client_ip=client_ip,
            )
            tracked_cid = tracked.connection_id
            await self._tracker.event(tracked_cid, "token_resolved", {
                "target": f"{session.target_host}:{session.target_port}",
            })

            resolved_host = await self._dns.resolve(session.target_host)
            if resolved_host != session.target_host:
                logger.info("DNS resolved %s -> %s", session.target_host, resolved_host)
                await self._tracker.event(tracked_cid, "dns_resolved", {
                    "host": session.target_host, "ip": resolved_host,
                })

            client_writer.write(build_x224_cc_ssl())
            await client_writer.drain()
            await self._tracker.event(tracked_cid, "x224_cc_sent")

            tls_ctx = _make_tls_context(
                self._cfg.proxy.cert_path,
                self._cfg.proxy.key_path,
            )
            await client_writer.start_tls(tls_ctx, server_hostname=None)
            configure_tcp_keepalive(client_writer)
            logger.info("Client TLS established (client=%s)", client_ip)
            await self._tracker.event(tracked_cid, "client_tls_established")

            backend = await connect_and_authenticate(
                target_host=resolved_host,
                target_port=session.target_port,
                username=session.username,
                password=session.password,
                fallback_domain=self._cfg.ldap.domain,
            )
            configure_tcp_keepalive(backend.writer)
            await self._tracker.event(tracked_cid, "credssp_authenticated")

            ctx = SessionContext(
                connection_id=tracked_cid,
                username=session.username,
                client_ip=client_ip,
                target_host=resolved_host,
                target_port=session.target_port,
                instance_id=self._cfg.instance.id,
                extra={"client_requested_protocols": client_requested_protocols},
            )
            await self._plugins.on_session_start(ctx)

            def _kill_requested() -> bool:
                return bool(self._sessions.client.get(f"rdp:kill:{tracked_cid}"))

            result: RelayResult = await relay_bidirectional(
                client_reader, client_writer,
                backend.reader, backend.writer,
                plugins=self._plugins,
                ctx=ctx,
                kill_checker=_kill_requested,
            )

            await self._plugins.on_session_end(ctx)
            await self._tracker.event(tracked_cid, "relay_finished", {
                "bytes_to_client": result.bytes_to_client,
                "bytes_to_backend": result.bytes_to_backend,
                "legs": [
                    {"direction": l.direction, "bytes": l.transferred, "reason": l.reason}
                    for l in result.legs
                ],
            })
            await self._tracker.finish(
                connection_id=tracked_cid,
                status="closed",
                disconnect_reason="normal",
                bytes_to_client=result.bytes_to_client,
                bytes_to_backend=result.bytes_to_backend,
            )
            logger.info("RDP session completed normally (client=%s cid=%s)", client_ip, tracked_cid)

        except Exception:
            logger.exception("RDP handling failed (client=%s)", client_ip)
            if tracked_cid is not None:
                try:
                    await self._tracker.event(tracked_cid, "error", {})
                    await self._tracker.finish(
                        connection_id=tracked_cid,
                        status="error",
                        disconnect_reason="exception",
                        bytes_to_client=0,
                        bytes_to_backend=0,
                    )
                except Exception:
                    logger.exception("Failed to finalize tracked connection %s", tracked_cid)
            abort_writer(client_writer)

    async def _resolve_client_ip(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> str:
        """Extract real client IP, using Proxy Protocol if enabled."""
        if self._cfg.rdp_relay.proxy_protocol:
            try:
                pp_info = await read_proxy_protocol(reader)
                logger.debug("Proxy Protocol: client=%s:%d", pp_info.src_addr, pp_info.src_port)
                return pp_info.src_addr
            except Exception:
                logger.warning("Failed to read Proxy Protocol header, falling back to peername")
        peer = writer.get_extra_info("peername")
        if isinstance(peer, tuple) and peer:
            return str(peer[0])
        return "unknown"
