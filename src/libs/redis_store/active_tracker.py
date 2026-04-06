from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import redis as redis_lib
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models.history import ConnectionEvent, ConnectionHistory

logger = logging.getLogger("rdpproxy.relay.tracker")


@dataclass
class TrackedConnection:
    connection_id: str
    username: str
    server_address: str
    server_port: int


class ConnectionTracker:
    """Tracks active RDP connections in Redis and persists history to PostgreSQL."""

    def __init__(
        self, *, db_sessionmaker: async_sessionmaker[AsyncSession] | None,
        redis_client: redis_lib.Redis | None, instance_id: str,
    ) -> None:
        self._db_factory = db_sessionmaker
        self._redis = redis_client
        self._instance_id = instance_id

    async def start(
        self, *, username: str, server_id: str | None, server_display: str | None,
        server_address: str, server_port: int, client_ip: str,
    ) -> TrackedConnection:
        cid = str(uuid.uuid4())
        parsed_server_id: uuid.UUID | None = None
        if server_id:
            try:
                parsed_server_id = uuid.UUID(str(server_id))
            except Exception:
                parsed_server_id = None
        if self._db_factory is not None:
            async with self._db_factory() as dbs:
                dbs.add(ConnectionHistory(
                    id=uuid.UUID(cid), instance_id=self._instance_id, username=username,
                    server_id=parsed_server_id, server_display=server_display,
                    server_address=server_address, server_port=server_port,
                    client_ip=client_ip, status="active",
                ))
                await dbs.commit()
        if self._redis is not None:
            payload = {
                "username": username, "server_display": server_display,
                "server_address": server_address, "server_port": int(server_port),
                "client_ip": client_ip, "started_at": datetime.now(timezone.utc).isoformat(),
                "instance_id": self._instance_id,
            }
            self._redis.set(f"rdp:active:{self._instance_id}:{cid}", json.dumps(payload, ensure_ascii=False), ex=24 * 3600)
        return TrackedConnection(connection_id=cid, username=username, server_address=server_address, server_port=server_port)

    async def event(self, connection_id: str, event_type: str, detail: dict[str, Any] | None = None) -> None:
        if self._db_factory is not None:
            async with self._db_factory() as dbs:
                dbs.add(ConnectionEvent(connection_id=uuid.UUID(connection_id), event_type=event_type, detail=detail or {}))
                await dbs.commit()

    async def finish(
        self, *, connection_id: str, status: str, disconnect_reason: str | None,
        bytes_to_client: int, bytes_to_backend: int,
    ) -> None:
        if self._db_factory is not None:
            async with self._db_factory() as dbs:
                await dbs.execute(
                    sa.update(ConnectionHistory)
                    .where(ConnectionHistory.id == uuid.UUID(connection_id))
                    .values(
                        ended_at=datetime.now(timezone.utc), status=status,
                        disconnect_reason=disconnect_reason,
                        bytes_to_client=int(bytes_to_client), bytes_to_backend=int(bytes_to_backend),
                    )
                )
                await dbs.commit()
        if self._redis is not None:
            self._redis.delete(f"rdp:active:{self._instance_id}:{connection_id}")

    async def reconcile_stale_active_on_startup(self) -> tuple[int, int]:
        """Mark leftover active sessions as error after relay restart."""
        db_updated = 0
        redis_deleted = 0

        if self._db_factory is not None:
            async with self._db_factory() as dbs:
                result = await dbs.execute(
                    sa.update(ConnectionHistory)
                    .where(
                        ConnectionHistory.instance_id == self._instance_id,
                        ConnectionHistory.status == "active",
                        ConnectionHistory.ended_at.is_(None),
                    )
                    .values(
                        ended_at=datetime.now(timezone.utc),
                        status="error",
                        disconnect_reason="relay-restart",
                    )
                )
                await dbs.commit()
                db_updated = int(result.rowcount or 0)

        if self._redis is not None:
            prefix = f"rdp:active:{self._instance_id}:"
            try:
                for key in self._redis.scan_iter(match=f"{prefix}*"):
                    self._redis.delete(key)
                    redis_deleted += 1
            except Exception:
                logger.exception("Failed to cleanup stale redis active sessions")

        return db_updated, redis_deleted
