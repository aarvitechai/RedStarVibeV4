import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7


class CardTemplate(Base):
    """Templates are data (Blueprint 22.5): a new template is an INSERT, not a deploy."""

    __tablename__ = "templates"
    __table_args__ = {"schema": "cards"}  # noqa: RUF012

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    occasion: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = {"schema": "cards"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(String(40), nullable=False)
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    photo_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    render_key: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="rendering")
    share_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
