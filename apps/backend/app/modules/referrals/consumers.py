"""Points are awarded from outbox events, idempotently (Blueprint 26.4)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, consumer
from app.modules.referrals import service


@consumer("accounts.user_signed_up", name="referrals.attribute")
async def attribute(db: AsyncSession, e: Event) -> None:
    code = e.payload.get("referral_code")
    if code:
        await service.attribute(db, uuid.UUID(e.payload["user_id"]), str(code))


@consumer("booking.created", name="referrals.qualify_on_booking")
async def qualify(db: AsyncSession, e: Event) -> None:
    await service.qualify_on_first_action(db, uuid.UUID(e.payload["customer_id"]))
