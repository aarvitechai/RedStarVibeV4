"""Order and event-booking notifications."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, consumer
from app.modules.notifications.service import deliver


@consumer("shop.order_placed", name="notifications.order_placed")
async def order_placed(db: AsyncSession, e: Event) -> None:
    p = e.payload
    rupees = p["total_paise"] / 100
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(p["business_owner_id"]),
        type="order.new",
        title=f"New order: ₹{rupees:,.0f}",
        link="/dashboard",
    )
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(p["customer_id"]),
        type="order.placed",
        title=f"Order placed: ₹{rupees:,.0f}",
        body="The shop will confirm soon.",
        link="/orders",
    )


@consumer("shop.order_status_changed", name="notifications.order_status")
async def order_status(db: AsyncSession, e: Event) -> None:
    p = e.payload
    target = p["customer_id"] if p["by"] == "business" else p["business_owner_id"]
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(target),
        type=f"order.{p['status']}",
        title=f"Order {p['status']}",
        link="/orders" if p["by"] == "business" else "/dashboard",
    )


@consumer("events.booked", name="notifications.event_booked")
async def event_booked(db: AsyncSession, e: Event) -> None:
    p = e.payload
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(p["organizer_owner_id"]),
        type="event.booked",
        title=f"Package enquiry: {p['package_name']}",
        body=p["event_date"],
        link="/dashboard",
    )


@consumer("events.vendor_invited", name="notifications.vendor_invited")
async def vendor_invited(db: AsyncSession, e: Event) -> None:
    p = e.payload
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(p["vendor_owner_id"]),
        type="event.vendor_invite",
        title=f"{p['organizer']} invited you to their vendor network",
        link="/dashboard",
    )
