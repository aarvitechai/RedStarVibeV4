"""Bookings: slots, create (idempotent, race-safe), status machine, reminders, expiry."""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.core.events import emit
from app.core.ids import uuid7
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.accounts.models import User
from app.modules.booking import repository as repo
from app.modules.booking.models import Booking
from app.modules.booking.schemas import BookingCreate, BookingOut, BookingPage, SlotOut, SlotsOut
from app.modules.booking.slots import Candidate, candidates, overlaps
from app.modules.business import service as business

# Allowed transitions and who may make them.
TRANSITIONS: dict[tuple[str, str], frozenset[str]] = {
    ("pending", "confirmed"): frozenset({"business"}),
    ("pending", "cancelled"): frozenset({"business", "customer"}),
    ("confirmed", "cancelled"): frozenset({"business", "customer"}),
    ("confirmed", "done"): frozenset({"business"}),
    ("pending", "expired"): frozenset({"system"}),
}
MAX_DAYS_AHEAD = 60
EXCLUSION_VIOLATION = "23P01"


def _sqlstate(exc: IntegrityError) -> str | None:
    orig = exc.orig
    return getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


def _day_window(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


async def _candidates_for(
    db: AsyncSession, business_id: uuid.UUID, service_id: uuid.UUID, day: date, now: datetime
) -> tuple[ZoneInfo, list[Candidate], dict[uuid.UUID, list[Booking]], list[uuid.UUID]]:
    b = await business.get_active_business(db, business_id)
    svc = await business.get_bookable_service(db, business_id, service_id)
    tz = ZoneInfo(b.timezone)
    today = now.astimezone(tz).date()
    if day < today or day > today + timedelta(days=MAX_DAYS_AHEAD):
        raise AppError("date_out_of_range", f"Choose a date from today up to {MAX_DAYS_AHEAD} days ahead.")
    hours = [(h.opens, h.closes) for h in await business.opening_hours(db, business_id) if h.weekday == day.weekday()]
    cands = candidates(day, tz, hours, svc.duration_min, svc.buffer_min, now)
    resources = await business.active_resource_ids(db, business_id)
    win_start, win_end = _day_window(day, tz)
    by_resource: dict[uuid.UUID, list[Booking]] = {r: [] for r in resources}
    for bk in await repo.active_in_window(db, business_id, win_start - timedelta(hours=12), win_end + timedelta(hours=12)):
        by_resource.setdefault(bk.resource_id, []).append(bk)
    return tz, cands, by_resource, resources


def _free(c: Candidate, resource: uuid.UUID, by_resource: dict[uuid.UUID, list[Booking]]) -> bool:
    return not any(
        overlaps(c.starts_at, c.blocks_until, bk.slot.lower, bk.slot.upper)  # type: ignore[arg-type]
        for bk in by_resource.get(resource, [])
    )


async def slots(
    db: AsyncSession, business_id: uuid.UUID, service_id: uuid.UUID, day: date, now: datetime | None = None
) -> SlotsOut:
    now = now or datetime.now(UTC)
    tz, cands, by_resource, resources = await _candidates_for(db, business_id, service_id, day, now)
    out = []
    for c in cands:
        free = sum(1 for r in resources if _free(c, r, by_resource))
        if free:
            out.append(SlotOut(starts_at=c.starts_at, ends_at=c.ends_at, free_resources=free))
    return SlotsOut(date=day, timezone=str(tz), service_id=service_id, slots=out)


async def create(
    db: AsyncSession, customer: User, data: BookingCreate, idempotency_key: str, now: datetime | None = None
) -> tuple[BookingOut, bool]:
    """Returns (booking, created). Replaying the same Idempotency-Key returns the original booking."""
    existing = await repo.by_idempotency_key(db, customer.id, idempotency_key)
    if existing is not None:
        return BookingOut.model_validate(existing), False
    await rate_limit.enforce("booking_create", str(customer.id), limit=10, window_s=3600)

    now = now or datetime.now(UTC)
    b = await business.get_active_business(db, data.business_id)
    if b.owner_id == customer.id:
        raise Forbidden("own_business", "You cannot book your own business.")
    svc = await business.get_bookable_service(db, b.id, data.service_id)
    tz = ZoneInfo(b.timezone)
    starts_at = data.starts_at.astimezone(UTC)
    day = starts_at.astimezone(tz).date()
    _, cands, by_resource, resources = await _candidates_for(db, b.id, svc.id, day, now)
    cand = next((c for c in cands if c.starts_at == starts_at), None)
    if cand is None:
        raise AppError("slot_unavailable", "This time is outside opening hours or too soon. Pick another slot.")
    if data.resource_id is not None:
        if data.resource_id not in resources:
            raise NotFound("resource_not_found", "That staff member or resource was not found.")
        order = [data.resource_id]
    else:
        order = [r for r in resources if _free(cand, r, by_resource)] or resources

    for resource_id in order:
        booking = Booking(
            id=uuid7(),
            business_id=b.id,
            resource_id=resource_id,
            service_id=svc.id,
            customer_id=customer.id,
            slot=Range(cand.starts_at, cand.blocks_until),
            starts_at=cand.starts_at,
            ends_at=cand.ends_at,
            status="pending",
            service_name=svc.name,
            price_paise=svc.price_paise,
            customer_note=data.customer_note,
            idempotency_key=idempotency_key,
        )
        try:
            async with db.begin_nested():  # savepoint: a lost race on this resource lets us try the next one
                db.add(booking)
                await db.flush()
        except IntegrityError as exc:
            if _sqlstate(exc) == EXCLUSION_VIOLATION:
                continue
            # Unique (customer_id, idempotency_key): a concurrent retry of the same request won.
            await db.rollback()
            replay = await repo.by_idempotency_key(db, customer.id, idempotency_key)
            if replay is not None:
                return BookingOut.model_validate(replay), False
            raise
        repo.add_history(db, booking.id, None, "pending", customer.id)
        emit(db, "booking.created", _event_payload(booking, b.owner_id))
        await db.commit()
        return BookingOut.model_validate(booking), True
    await db.rollback()
    raise Conflict("slot_taken", "Someone just booked this slot. Please pick another time.")


def _event_payload(bk: Booking, owner_id: uuid.UUID) -> dict[str, str]:
    return {
        "booking_id": str(bk.id),
        "business_id": str(bk.business_id),
        "business_owner_id": str(owner_id),
        "customer_id": str(bk.customer_id),
        "service_name": bk.service_name,
        "starts_at": bk.starts_at.isoformat(),
        "status": bk.status,
    }


async def transition(
    db: AsyncSession, actor: User, booking_id: uuid.UUID, to_status: str, now: datetime | None = None
) -> BookingOut:
    now = now or datetime.now(UTC)
    bk = await repo.get(db, booking_id, lock=True)
    if bk is None:
        raise NotFound("booking_not_found", "Booking not found.")
    b = await business.get_active_business(db, bk.business_id)
    if actor.id == b.owner_id:
        role = "business"
    elif actor.id == bk.customer_id:
        role = "customer"
    else:
        raise NotFound("booking_not_found", "Booking not found.")  # never confirm the booking exists
    allowed = TRANSITIONS.get((bk.status, to_status))
    if allowed is None or role not in allowed:
        raise Conflict("invalid_transition", f"A {bk.status} booking cannot be marked {to_status}.")
    if role == "customer" and to_status == "cancelled" and bk.starts_at <= now:
        raise Conflict("too_late_to_cancel", "This booking has already started.")
    if to_status == "done" and bk.starts_at > now:
        raise Conflict("not_started", "A booking can be completed only after it starts.")
    old = bk.status
    bk.status = to_status
    bk.updated_at = now
    repo.add_history(db, bk.id, old, to_status, actor.id)
    emit(db, "booking.status_changed", {**_event_payload(bk, b.owner_id), "from": old, "by": role})
    await db.commit()
    return BookingOut.model_validate(bk)


async def my_bookings(db: AsyncSession, customer: User, cursor: str | None, limit: int) -> BookingPage:
    c = decode_cursor(cursor)
    after = (datetime.fromisoformat(c["s"]), uuid.UUID(c["i"])) if c else None
    rows = await repo.for_customer(db, customer.id, after=after, limit=limit)
    nxt = encode_cursor({"s": rows[-1].starts_at.isoformat(), "i": str(rows[-1].id)}) if len(rows) == limit else None
    return BookingPage(items=[BookingOut.model_validate(r) for r in rows], next_cursor=nxt)


async def business_day(db: AsyncSession, owner: User, business_id: uuid.UUID, day: date) -> list[BookingOut]:
    b = await business.owned(db, business_id, owner)
    start, end = _day_window(day, ZoneInfo(b.timezone))
    return [BookingOut.model_validate(r) for r in await repo.for_business(db, b.id, start, end)]


# --- Interface for other modules ---


async def completed_booking_for(db: AsyncSession, booking_id: uuid.UUID, customer_id: uuid.UUID) -> Booking:
    bk = await repo.get(db, booking_id)
    if bk is None or bk.customer_id != customer_id:
        raise NotFound("booking_not_found", "Booking not found.")
    if bk.status != "done":
        raise Conflict("booking_not_done", "You can review a booking after it is completed.")
    return bk


# --- Scheduled jobs (beat) ---


async def send_reminders(db: AsyncSession, now: datetime | None = None, ahead: timedelta = timedelta(hours=2)) -> int:
    now = now or datetime.now(UTC)
    rows = await repo.due_for_reminder(db, now, now + ahead)
    for bk in rows:
        b = await business.get_active_business(db, bk.business_id)
        bk.reminded_at = now
        emit(db, "booking.reminder_due", _event_payload(bk, b.owner_id))
    await db.commit()
    return len(rows)


async def expire_stale(db: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    rows = await repo.stale_pending(db, now)
    for bk in rows:
        b = await business.get_active_business(db, bk.business_id)
        bk.status = "expired"
        bk.updated_at = now
        repo.add_history(db, bk.id, "pending", "expired", None)
        emit(db, "booking.status_changed", {**_event_payload(bk, b.owner_id), "from": "pending", "by": "system"})
    await db.commit()
    return len(rows)
