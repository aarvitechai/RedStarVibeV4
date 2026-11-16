import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = {"schema": "albums"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    visibility: Mapped[str] = mapped_column(String(10), nullable=False, default="link")  # private | link
    share_token: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    slideshow_key: Mapped[str | None] = mapped_column(String(200))
    slideshow_status: Mapped[str] = mapped_column(String(12), nullable=False, default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AlbumItem(Base):
    __tablename__ = "items"
    __table_args__ = {"schema": "albums"}  # noqa: RUF012

    album_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[str | None] = mapped_column(String(200))
