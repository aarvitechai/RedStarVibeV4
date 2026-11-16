import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReferralCode(Base):
    __tablename__ = "codes"
    __table_args__ = {"schema": "referrals"}  # noqa: RUF012

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Referral(Base):
    """One referrer per new account (referee_id is the primary key). Qualifies only after a real action."""

    __tablename__ = "referrals"
    __table_args__ = {"schema": "referrals"}  # noqa: RUF012

    referee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    referrer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PointsEntry(Base):
    """Append-only Star Points ledger. (reason, ref_id, user_id) is unique, so an award can never be paid twice."""

    __tablename__ = "points_ledger"
    __table_args__ = (UniqueConstraint("user_id", "reason", "ref_id", name="ux_points_once"), {"schema": "referrals"})

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
