import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = {"schema": "social"}  # noqa: RUF012

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    bio: Mapped[str | None] = mapped_column(String(300))
    avatar_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    website: Mapped[str | None] = mapped_column(String(200))
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = {"schema": "social"}  # noqa: RUF012

    follower_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    followee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")  # active | pending
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = {"schema": "social"}  # noqa: RUF012

    blocker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    blocked_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Mute(Base):
    __tablename__ = "mutes"
    __table_args__ = {"schema": "social"}  # noqa: RUF012

    muter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    muted_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
