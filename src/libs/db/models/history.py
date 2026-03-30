from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ConnectionHistory(Base):
    __tablename__ = "connection_history"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instance_id: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    username: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("rdp_servers.id", ondelete="SET NULL"), nullable=True,
    )
    server_display: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    server_address: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    server_port: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    client_ip: Mapped[str] = mapped_column(sa.String(45), nullable=False)
    started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    ended_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    bytes_to_client: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, server_default=sa.text("0"))
    bytes_to_backend: Mapped[int] = mapped_column(sa.BigInteger, nullable=False, server_default=sa.text("0"))
    disconnect_reason: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    status: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default=sa.text("'active'"))

    events: Mapped[list[ConnectionEvent]] = relationship(
        back_populates="connection", cascade="all, delete-orphan", order_by="ConnectionEvent.ts",
    )

    __table_args__ = (
        sa.Index("idx_conn_history_user", "username"),
        sa.Index("idx_conn_history_started", "started_at"),
    )


class ConnectionEvent(Base):
    __tablename__ = "connection_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid(as_uuid=True), sa.ForeignKey("connection_history.id", ondelete="CASCADE"), nullable=False,
    )
    ts: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    event_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))

    connection: Mapped[ConnectionHistory] = relationship(back_populates="events")

    __table_args__ = (sa.Index("idx_conn_events_conn_id", "connection_id"),)
