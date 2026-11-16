"""Turns booking and review events into notifications. Runs in the worker via the outbox dispatcher."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, consumer
from app.modules.notifications.service import deliver

IST = ZoneInfo("Asia/Kolkata")


def _when(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(IST).strftime("%a %d %b, %I:%M %p")


@consumer("booking.created", name="notifications.booking_created")
async def booking_created(db: AsyncSession, e: Event) -> None:
    p = e.payload
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(p["business_owner_id"]),
        type="booking.new",
        title=f"New booking: {p['service_name']}",
        body=_when(p["starts_at"]),
        link="/dashboard",
    )
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(p["customer_id"]),
        type="booking.requested",
        title=f"Booking requested: {p['service_name']}",
        body=f"{_when(p['starts_at'])} · waiting for confirmation",
        link="/bookings",
    )


_STATUS_TEXT = {"confirmed": "confirmed", "cancelled": "cancelled", "done": "completed", "expired": "expired"}


@consumer("booking.status_changed", name="notifications.booking_status")
async def booking_status(db: AsyncSession, e: Event) -> None:
    p = e.payload
    text = _STATUS_TEXT.get(p["status"], p["status"])
    # Notify the other side of the change (the actor already knows).
    if p.get("by") != "customer":
        await deliver(
            db,
            event_id=e.event_id,
            user_id=uuid.UUID(p["customer_id"]),
            type=f"booking.{p['status']}",
            title=f"Booking {text}: {p['service_name']}",
            body=_when(p["starts_at"]),
            link="/bookings",
        )
    if p.get("by") != "business":
        await deliver(
            db,
            event_id=e.event_id,
            user_id=uuid.UUID(p["business_owner_id"]),
            type=f"booking.{p['status']}",
            title=f"Booking {text}: {p['service_name']}",
            body=_when(p["starts_at"]),
            link="/dashboard",
        )


@consumer("booking.reminder_due", name="notifications.booking_reminder")
async def booking_reminder(db: AsyncSession, e: Event) -> None:
    p = e.payload
    for uid, link in ((p["customer_id"], "/bookings"), (p["business_owner_id"], "/dashboard")):
        await deliver(
            db,
            event_id=e.event_id,
            user_id=uuid.UUID(uid),
            type="booking.reminder",
            title=f"Reminder: {p['service_name']}",
            body=_when(p["starts_at"]),
            link=link,
        )
