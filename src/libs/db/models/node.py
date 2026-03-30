from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ClusterNode(Base):
    """Tracks cluster node registrations and status snapshots in PostgreSQL."""

    __tablename__ = "cluster_nodes"

    instance_id: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    hostname: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    ip: Mapped[str] = mapped_column(sa.String(45), nullable=False)
    services: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    resources: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    last_heartbeat: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    registered_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
