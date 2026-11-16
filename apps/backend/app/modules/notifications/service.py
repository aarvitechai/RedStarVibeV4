"""Notifications. Channel interface: in-app now; web push, email, SMS and WhatsApp plug in behind `deliver()`."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.notifications.models import Notification


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    unread: int
    next_cursor: str | None


async def deliver(
    db: AsyncSession,
    *,
    event_id: uuid.UUID,
    user_id: uuid.UUID,
    type: str,
    title: str,
    body: str | None = None,
    link: str | None = None,
    channel: str = "inapp",
) -> bool:
    """Idempotent: returns False if this event already notified this user on this channel."""
    key = f"{event_id}:{channel}:{user_id}"
    inserted = await db.scalar(
        insert(Notification)
        .values(id=uuid.uuid4(), user_id=user_id, type=type, title=title, body=body, link=link, dedupe_key=key)
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(Notification.id)
    )
    return inserted is not None


async def list_for(db: AsyncSession, user_id: uuid.UUID, cursor: str | None, limit: int) -> NotificationPage:
    stmt = select(Notification).where(Notification.user_id == user_id)
    c = decode_cursor(cursor)
    if c:
        at, nid = datetime.fromisoformat(c["t"]), uuid.UUID(c["i"])
        stmt = stmt.where(or_(Notification.created_at < at, and_(Notification.created_at == at, Notification.id < nid)))
    rows = (await db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit))).all()
    unread = await db.scalar(select(func.count()).where(Notification.user_id == user_id, Notification.read_at.is_(None)))
    nxt = encode_cursor({"t": rows[-1].created_at.isoformat(), "i": str(rows[-1].id)}) if len(rows) == limit else None
    return NotificationPage(items=[NotificationOut.model_validate(r) for r in rows], unread=int(unread or 0), next_cursor=nxt)


async def mark_read(db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> None:
    result = await db.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.user_id == user_id)
        .values(read_at=func.coalesce(Notification.read_at, datetime.now(UTC)))
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise NotFound("notification_not_found", "Notification not found.")
    await db.commit()
