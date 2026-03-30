from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class RdpServer(Base):
    __tablename__ = "rdp_servers"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tech_name: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    address: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    port: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("3389"))
    is_enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())

    group_bindings: Mapped[list[ServerGroupBinding]] = relationship(back_populates="server", cascade="all, delete-orphan")


class ServerGroupBinding(Base):
    __tablename__ = "server_group_bindings"

    server_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), sa.ForeignKey("rdp_servers.id", ondelete="CASCADE"), primary_key=True)
    ad_group_guid: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True)

    server: Mapped[RdpServer] = relationship(back_populates="group_bindings")
