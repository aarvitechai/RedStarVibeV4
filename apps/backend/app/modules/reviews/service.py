"""Reviews after completed bookings, and business replies. Depends on booking and business services only."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, NotFound
from app.core.events import emit
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.accounts.models import User
from app.modules.booking import service as booking
from app.modules.business import service as business
from app.modules.reviews.models import Review


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int = Field(ge=1, le=5)
    body: str | None = Field(default=None, max_length=1000)


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=1000)


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    business_id: uuid.UUID
    customer_name: str
    rating: int
    body: str | None
    reply_body: str | None
    replied_at: datetime | None
    created_at: datetime


class ReviewPage(BaseModel):
    items: list[ReviewOut]
    average: float | None
    count: int
    next_cursor: str | None


async def create(db: AsyncSession, customer: User, booking_id: uuid.UUID, data: ReviewIn) -> ReviewOut:
    bk = await booking.completed_booking_for(db, booking_id, customer.id)
    review = Review(
        booking_id=bk.id,
        business_id=bk.business_id,
        customer_id=customer.id,
        customer_name=customer.display_name,
        rating=data.rating,
        body=data.body,
    )
    db.add(review)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict("already_reviewed", "You already reviewed this booking.") from exc
    emit(db, "reviews.created", {"review_id": str(review.id), "business_id": str(bk.business_id), "rating": data.rating})
    await db.commit()
    return ReviewOut.model_validate(review)


async def reply(db: AsyncSession, owner: User, review_id: uuid.UUID, data: ReplyIn) -> ReviewOut:
    review = await db.get(Review, review_id)
    if review is None:
        raise NotFound("review_not_found", "Review not found.")
    await business.owned(db, review.business_id, owner)  # 404 unless owner
    if review.reply_body is not None:
        raise Conflict("already_replied", "You already replied to this review.")
    review.reply_body, review.replied_at = data.body, datetime.now(UTC)
    await db.commit()
    return ReviewOut.model_validate(review)


async def for_business(db: AsyncSession, business_id: uuid.UUID, cursor: str | None, limit: int) -> ReviewPage:
    base = and_(Review.business_id == business_id, Review.status == "published")
    stmt = select(Review).where(base)
    c = decode_cursor(cursor)
    if c:
        at, rid = datetime.fromisoformat(c["t"]), uuid.UUID(c["i"])
        stmt = stmt.where(or_(Review.created_at < at, and_(Review.created_at == at, Review.id < rid)))
    rows = (await db.scalars(stmt.order_by(Review.created_at.desc(), Review.id.desc()).limit(limit))).all()
    avg, count = (await db.execute(select(func.avg(Review.rating), func.count()).where(base))).one()
    nxt = encode_cursor({"t": rows[-1].created_at.isoformat(), "i": str(rows[-1].id)}) if len(rows) == limit else None
    return ReviewPage(
        items=[ReviewOut.model_validate(r) for r in rows],
        average=round(float(avg), 2) if avg else None,
        count=int(count),
        next_cursor=nxt,
    )
