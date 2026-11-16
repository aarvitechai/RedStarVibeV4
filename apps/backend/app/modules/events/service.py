"""Event organizers: packages (Silver/Gold/Platinum/custom), vendor network, and the unified calendar.

Booking a package creates an availability *hold* for the organizer and for every vendor in the package, in one
transaction. `events.holds` has EXCLUDE USING gist (business_id WITH =, slot WITH &&) for active holds, so a
vendor can never be committed to two events at once, even across different organizers (Blueprint 22.3, M6).
Unpaid pending bookings release their holds when they expire.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import TSTZRANGE, UUID, Range, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core import rate_limit
from app.core.database import Base
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.events import emit
from app.core.ids import uuid7
from app.modules.accounts.models import User
from app.modules.business import service as business

PENDING_HOLD_TTL = timedelta(hours=48)
EXCLUSION_VIOLATION = "23P01"


class Package(Base):
    __tablename__ = "packages"
    __table_args__ = {"schema": "events"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    tier: Mapped[str] = mapped_column(String(10), nullable=False, default="custom")
    description: Mapped[str | None] = mapped_column(String(2000))
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_guests: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False, default="10:00")
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PackageItem(Base):
    __tablename__ = "package_items"
    __table_args__ = {"schema": "events"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    vendor_business_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class VendorLink(Base):
    __tablename__ = "vendor_links"
    __table_args__ = {"schema": "events"}  # noqa: RUF012
    organizer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="invited")
    terms: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EventBooking(Base):
    __tablename__ = "event_bookings"
    __table_args__ = {"schema": "events"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    organizer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    guests: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    payment_status: Mapped[str] = mapped_column(String(12), nullable=False, default="unpaid")
    price_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    package_name: Mapped[str] = mapped_column(String(120), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Hold(Base):
    __tablename__ = "holds"
    __table_args__ = {"schema": "events"}  # noqa: RUF012
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    slot: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PackageItemIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    vendor_slug: str | None = Field(default=None, max_length=60)


class PackageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    tier: Literal["silver", "gold", "platinum", "custom"] = "custom"
    description: str | None = Field(default=None, max_length=2000)
    price_paise: int = Field(ge=0, le=10_000_000_000)
    max_guests: int = Field(ge=1, le=100_000)
    start_time: str = Field(default="10:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_hours: int = Field(default=8, ge=1, le=24)
    items: list[PackageItemIn] = Field(default_factory=list, max_length=40)


class PackageItemOut(BaseModel):
    label: str
    vendor: str | None


class PackageOut(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    name: str
    tier: str
    description: str | None
    price_paise: int
    max_guests: int
    start_time: str
    duration_hours: int
    items: list[PackageItemOut]


class VendorOut(BaseModel):
    organizer: str
    vendor: str
    status: str
    terms: str | None


class EventBookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    package_id: uuid.UUID
    event_date: date
    guests: int = Field(ge=1, le=100_000)
    note: str | None = Field(default=None, max_length=500)


class EventBookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    package_id: uuid.UUID
    organizer_id: uuid.UUID
    customer_id: uuid.UUID
    package_name: str
    event_date: date
    guests: int
    status: str
    payment_status: str
    price_paise: int
    expires_at: datetime | None


class HoldOut(BaseModel):
    event_booking_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    package_name: str
    as_vendor: bool


async def _package_out(db: AsyncSession, p: Package) -> PackageOut:
    items = (await db.scalars(select(PackageItem).where(PackageItem.package_id == p.id))).all()
    vendor_ids = [i.vendor_business_id for i in items if i.vendor_business_id]
    names = {v: (await business.get_active_business(db, v)).name for v in vendor_ids}
    return PackageOut(
        id=p.id,
        business_id=p.business_id,
        name=p.name,
        tier=p.tier,
        description=p.description,
        price_paise=p.price_paise,
        max_guests=p.max_guests,
        start_time=p.start_time,
        duration_hours=p.duration_hours,
        items=[
            PackageItemOut(label=i.label, vendor=names.get(i.vendor_business_id) if i.vendor_business_id else None) for i in items
        ],
    )


async def _business_by_slug(db: AsyncSession, slug: str) -> uuid.UUID:
    pub = await business.public_by_slug(db, slug)
    return pub.id


async def create_package(db: AsyncSession, user: User, business_id: uuid.UUID, data: PackageIn) -> PackageOut:
    b = await business.owned(db, business_id, user)
    p = Package(id=uuid7(), business_id=b.id, **data.model_dump(exclude={"items"}))
    db.add(p)
    for item in data.items:
        vendor_id = None
        if item.vendor_slug:
            vendor_id = await _business_by_slug(db, item.vendor_slug.lower())
            link = await db.get(VendorLink, (b.id, vendor_id))
            if link is None or link.status != "accepted":
                raise AppError("vendor_not_accepted", f"{item.vendor_slug} has not accepted your vendor invite yet.")
        db.add(PackageItem(package_id=p.id, label=item.label, vendor_business_id=vendor_id))
    await db.commit()
    return await _package_out(db, p)


async def packages(db: AsyncSession, business_id: uuid.UUID) -> list[PackageOut]:
    rows = (
        await db.scalars(
            select(Package).where(Package.business_id == business_id, Package.active.is_(True)).order_by(Package.price_paise)
        )
    ).all()
    return [await _package_out(db, p) for p in rows]


async def invite_vendor(db: AsyncSession, user: User, organizer_id: uuid.UUID, vendor_slug: str, terms: str | None) -> VendorOut:
    org = await business.owned(db, organizer_id, user)
    vendor_id = await _business_by_slug(db, vendor_slug.lower())
    if vendor_id == org.id:
        raise AppError("self_vendor", "You cannot invite your own business.")
    await db.execute(
        insert(VendorLink)
        .values(organizer_id=org.id, vendor_id=vendor_id, status="invited", terms=terms)
        .on_conflict_do_nothing()
    )
    vendor = await business.get_active_business(db, vendor_id)
    emit(db, "events.vendor_invited", {"organizer": org.name, "vendor_owner_id": str(vendor.owner_id)})
    await db.commit()
    link = await db.get(VendorLink, (org.id, vendor_id))
    assert link is not None
    return VendorOut(organizer=org.slug, vendor=vendor.slug, status=link.status, terms=link.terms)


async def answer_invite(
    db: AsyncSession, user: User, vendor_business_id: uuid.UUID, organizer_slug: str, accept: bool
) -> VendorOut:
    vendor = await business.owned(db, vendor_business_id, user)
    org_id = await _business_by_slug(db, organizer_slug.lower())
    link = await db.get(VendorLink, (org_id, vendor.id))
    if link is None or link.status != "invited":
        raise NotFound("invite_not_found", "Invite not found.")
    link.status = "accepted" if accept else "declined"
    await db.commit()
    return VendorOut(organizer=organizer_slug.lower(), vendor=vendor.slug, status=link.status, terms=link.terms)


async def vendor_links(db: AsyncSession, user: User, business_id: uuid.UUID) -> list[VendorOut]:
    b = await business.owned(db, business_id, user)
    rows = (await db.scalars(select(VendorLink).where(or_(VendorLink.organizer_id == b.id, VendorLink.vendor_id == b.id)))).all()
    out = []
    for r in rows:
        org = await business.get_active_business(db, r.organizer_id)
        ven = await business.get_active_business(db, r.vendor_id)
        out.append(VendorOut(organizer=org.slug, vendor=ven.slug, status=r.status, terms=r.terms))
    return out


def _slot(day: date, p: Package, tz: str) -> Range[datetime]:
    hh, mm = (int(x) for x in p.start_time.split(":"))
    start = datetime.combine(day, time(hh, mm), tzinfo=ZoneInfo(tz))
    return Range(start.astimezone(UTC), (start + timedelta(hours=p.duration_hours)).astimezone(UTC))


async def book(db: AsyncSession, customer: User, data: EventBookingIn, idempotency_key: str) -> tuple[EventBookingOut, bool]:
    existing = await db.scalar(
        select(EventBooking).where(EventBooking.customer_id == customer.id, EventBooking.idempotency_key == idempotency_key)
    )
    if existing:
        return EventBookingOut.model_validate(existing), False
    await rate_limit.enforce("event_booking", str(customer.id), limit=10, window_s=3600)
    p = await db.get(Package, data.package_id)
    if p is None or not p.active:
        raise NotFound("package_not_found", "Package not found.")
    org = await business.get_active_business(db, p.business_id)
    if org.owner_id == customer.id:
        raise Forbidden("own_business", "You cannot book your own package.")
    if data.guests > p.max_guests:
        raise AppError("too_many_guests", f"This package is for up to {p.max_guests} guests.")
    today = datetime.now(ZoneInfo(org.timezone)).date()
    if data.event_date <= today or data.event_date > today + timedelta(days=540):
        raise AppError("invalid_date", "Choose a future date within 18 months.")
    eb = EventBooking(
        id=uuid7(),
        package_id=p.id,
        organizer_id=org.id,
        customer_id=customer.id,
        event_date=data.event_date,
        guests=data.guests,
        price_paise=p.price_paise,
        package_name=p.name,
        note=data.note,
        idempotency_key=idempotency_key,
        expires_at=datetime.now(UTC) + PENDING_HOLD_TTL,
    )
    db.add(eb)
    slot = _slot(data.event_date, p, org.timezone)
    vendor_ids = {
        i.vendor_business_id
        for i in (await db.scalars(select(PackageItem).where(PackageItem.package_id == p.id))).all()
        if i.vendor_business_id
    }
    for bid in [org.id, *sorted(vendor_ids)]:
        db.add(Hold(event_booking_id=eb.id, business_id=bid, slot=slot, active=True))
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) == EXCLUSION_VIOLATION or getattr(exc.orig, "pgcode", None) == EXCLUSION_VIOLATION:
            raise Conflict("date_unavailable", "The venue or a vendor in this package is already booked on that date.") from exc
        replay = await db.scalar(
            select(EventBooking).where(EventBooking.customer_id == customer.id, EventBooking.idempotency_key == idempotency_key)
        )
        if replay:
            return EventBookingOut.model_validate(replay), False
        raise
    emit(
        db,
        "events.booked",
        {
            "event_booking_id": str(eb.id),
            "organizer_owner_id": str(org.owner_id),
            "customer_id": str(customer.id),
            "package_name": p.name,
            "event_date": data.event_date.isoformat(),
        },
    )
    await db.commit()
    return EventBookingOut.model_validate(eb), True


async def _release(db: AsyncSession, eb_id: uuid.UUID) -> None:
    await db.execute(update(Hold).where(Hold.event_booking_id == eb_id).values(active=False))


async def set_status(db: AsyncSession, actor: User, eb_id: uuid.UUID, to: str) -> EventBookingOut:
    eb = await db.get(EventBooking, eb_id, with_for_update=True)
    if eb is None:
        raise NotFound("booking_not_found", "Booking not found.")
    org = await business.get_active_business(db, eb.organizer_id)
    allowed = {
        ("pending", "confirmed"): {"business"},
        ("pending", "cancelled"): {"business", "customer"},
        ("confirmed", "cancelled"): {"business", "customer"},
        ("confirmed", "done"): {"business"},
    }
    role = "business" if actor.id == org.owner_id else "customer" if actor.id == eb.customer_id else None
    if role is None:
        raise NotFound("booking_not_found", "Booking not found.")
    if role not in allowed.get((eb.status, to), set()):
        raise Conflict("invalid_transition", f"A {eb.status} booking cannot be marked {to}.")
    if to == "cancelled":
        await _release(db, eb.id)
    if to == "confirmed":
        eb.expires_at = None  # confirmed bookings keep their holds
    eb.status = to
    await db.commit()
    return EventBookingOut.model_validate(eb)


async def expire_holds(db: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    rows = (
        await db.scalars(
            select(EventBooking)
            .where(EventBooking.status == "pending", EventBooking.expires_at <= now)
            .with_for_update(skip_locked=True)
            .limit(500)
        )
    ).all()
    for eb in rows:
        eb.status = "expired"
        await _release(db, eb.id)
    await db.commit()
    return len(rows)


async def my_event_bookings(db: AsyncSession, customer: User) -> list[EventBookingOut]:
    rows = (
        await db.scalars(
            select(EventBooking).where(EventBooking.customer_id == customer.id).order_by(EventBooking.event_date.desc()).limit(50)
        )
    ).all()
    return [EventBookingOut.model_validate(r) for r in rows]


async def organizer_bookings(db: AsyncSession, owner: User, business_id: uuid.UUID) -> list[EventBookingOut]:
    b = await business.owned(db, business_id, owner)
    rows = (
        await db.scalars(
            select(EventBooking).where(EventBooking.organizer_id == b.id).order_by(EventBooking.event_date).limit(200)
        )
    ).all()
    return [EventBookingOut.model_validate(r) for r in rows]


async def calendar(db: AsyncSession, owner: User, business_id: uuid.UUID, start: date, days: int) -> list[HoldOut]:
    """Unified calendar: the business's own events plus events it is booked on as a vendor. A vendor sees only
    its own holds, never the organizer's customer details."""
    b = await business.owned(db, business_id, owner)
    win = Range(datetime.combine(start, time(0), tzinfo=UTC), datetime.combine(start + timedelta(days=days), time(0), tzinfo=UTC))
    rows = (
        await db.execute(
            select(Hold, EventBooking.package_name, EventBooking.organizer_id)
            .join(EventBooking, EventBooking.id == Hold.event_booking_id)
            .where(Hold.business_id == b.id, Hold.active.is_(True), Hold.slot.overlaps(win))
            .order_by(func.lower(Hold.slot))
        )
    ).all()
    return [
        HoldOut(
            event_booking_id=h.event_booking_id,
            starts_at=h.slot.lower,
            ends_at=h.slot.upper,
            package_name=name,
            as_vendor=org_id != b.id,
        )
        for h, name, org_id in rows
    ]


# --- Interface for payments ---


async def booking_for_payment(db: AsyncSession, customer_id: uuid.UUID, eb_id: uuid.UUID) -> EventBooking:
    eb = await db.get(EventBooking, eb_id)
    if eb is None or eb.customer_id != customer_id:
        raise NotFound("booking_not_found", "Booking not found.")
    if eb.status not in ("pending", "confirmed") or eb.payment_status == "paid":
        raise Conflict("booking_not_payable", "This booking cannot be paid.")
    return eb


async def mark_advance_paid(db: AsyncSession, eb_id: uuid.UUID) -> None:
    """An advance payment locks the date (Blueprint 22.3): the hold no longer expires."""
    await db.execute(update(EventBooking).where(and_(EventBooking.id == eb_id)).values(payment_status="paid", expires_at=None))
