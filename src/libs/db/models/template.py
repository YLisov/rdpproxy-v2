from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class RdpTemplate(Base):
    __tablename__ = "rdp_templates"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(128), unique=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())

    group_bindings: Mapped[list[TemplateGroupBinding]] = relationship(back_populates="template", cascade="all, delete-orphan")

    __table_args__ = (sa.CheckConstraint("priority >= 0", name="ck_rdp_templates_priority_nonneg"),)


class TemplateGroupBinding(Base):
    __tablename__ = "template_group_bindings"

    template_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), sa.ForeignKey("rdp_templates.id", ondelete="CASCADE"), primary_key=True)
    ad_group_guid: Mapped[uuid.UUID] = mapped_column(sa.Uuid(as_uuid=True), primary_key=True)

    template: Mapped[RdpTemplate] = relationship(back_populates="group_bindings")
