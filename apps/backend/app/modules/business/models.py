import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Float, Integer, LargeBinary, SmallInteger, String, Text, Time, func
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7

CATEGORIES = (
    "electrician",
    "plumber",
    "welder",
    "driver",
    "carpenter",
    "painter",
    "beauty",
    "tailor",
    "tutor",
    "home_food",
    "bakery",
    "shop",
    "photographer",
    "event",
    "other",
)


class Business(Base):
    """`location` (PostGIS geography) is a generated column computed from lat/lng in migration 0003."""

    __tablename__ = "businesses"
    __table_args__ = {"schema": "business"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    tagline: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    phone_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    area: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    service_radius_km: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    timezone: Mapped[str] = mapped_column(String(40), nullable=False, default="Asia/Kolkata")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Service(Base):
    __tablename__ = "services"
    __table_args__ = {"schema": "business"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BusinessHours(Base):
    __tablename__ = "hours"
    __table_args__ = {"schema": "business"}  # noqa: RUF012

    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    weekday: Mapped[int] = mapped_column(SmallInteger, primary_key=True)  # 0 = Monday
    opens: Mapped[time] = mapped_column(Time, primary_key=True)
    closes: Mapped[time] = mapped_column(Time, nullable=False)


class Resource(Base):
    """Something that can be booked: a worker, a vehicle, a chair, a lawn."""

    __tablename__ = "resources"
    __table_args__ = {"schema": "business"}  # noqa: RUF012

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
