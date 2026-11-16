import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.booking.models import ACTIVE_STATUSES, Booking, BookingStatusHistory


async def active_in_window(db: AsyncSession, business_id: uuid.UUID, start: datetime, end: datetime) -> Sequence[Booking]:
    return (
        await db.scalars(
            select(Booking).where(
                Booking.business_id == business_id,
                Booking.status.in_(ACTIVE_STATUSES),
                Booking.slot.overlaps(Range(start, end)),
            )
        )
    ).all()


async def get(db: AsyncSession, booking_id: uuid.UUID, *, lock: bool = False) -> Booking | None:
    stmt = select(Booking).where(Booking.id == booking_id)
    if lock:
        stmt = stmt.with_for_update()
    return await db.scalar(stmt)


async def by_idempotency_key(db: AsyncSession, customer_id: uuid.UUID, key: str) -> Booking | None:
    return await db.scalar(select(Booking).where(Booking.customer_id == customer_id, Booking.idempotency_key == key))


async def for_customer(
    db: AsyncSession, customer_id: uuid.UUID, *, after: tuple[datetime, uuid.UUID] | None, limit: int
) -> Sequence[Booking]:
    stmt = select(Booking).where(Booking.customer_id == customer_id)
    if after:
        stmt = stmt.where(or_(Booking.starts_at < after[0], and_(Booking.starts_at == after[0], Booking.id < after[1])))
    return (await db.scalars(stmt.order_by(Booking.starts_at.desc(), Booking.id.desc()).limit(limit))).all()


async def for_business(db: AsyncSession, business_id: uuid.UUID, start: datetime, end: datetime) -> Sequence[Booking]:
    return (
        await db.scalars(
            select(Booking)
            .where(Booking.business_id == business_id, Booking.starts_at >= start, Booking.starts_at < end)
            .order_by(Booking.starts_at)
        )
    ).all()


def add_history(
    db: AsyncSession, booking_id: uuid.UUID, from_status: str | None, to_status: str, actor_id: uuid.UUID | None
) -> None:
    db.add(BookingStatusHistory(booking_id=booking_id, from_status=from_status, to_status=to_status, actor_id=actor_id))


async def due_for_reminder(db: AsyncSession, now: datetime, until: datetime, limit: int = 200) -> Sequence[Booking]:
    return (
        await db.scalars(
            select(Booking)
            .where(
                Booking.status == "confirmed", Booking.reminded_at.is_(None), Booking.starts_at > now, Booking.starts_at <= until
            )
            .order_by(Booking.starts_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()


async def stale_pending(db: AsyncSession, now: datetime, limit: int = 500) -> Sequence[Booking]:
    return (
        await db.scalars(
            select(Booking)
            .where(Booking.status == "pending", Booking.starts_at <= now)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
