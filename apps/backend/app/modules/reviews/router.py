import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, CurrentUser, require_permission
from app.modules.accounts.models import User
from app.modules.reviews import service
from app.modules.reviews.service import ReplyIn, ReviewIn, ReviewOut, ReviewPage

router = APIRouter(tags=["reviews"])


@router.post("/bookings/{booking_id}/review", response_model=ReviewOut, status_code=201)
async def review_booking(booking_id: uuid.UUID, body: ReviewIn, db: DB, user: CurrentUser) -> ReviewOut:
    return await service.create(db, user, booking_id, body)


@router.get("/businesses/{business_id}/reviews", response_model=ReviewPage)
async def business_reviews(
    business_id: uuid.UUID, db: DB, cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> ReviewPage:
    return await service.for_business(db, business_id, cursor, limit)


@router.post("/reviews/{review_id}/reply", response_model=ReviewOut)
async def reply(
    review_id: uuid.UUID, body: ReplyIn, db: DB, user: Annotated[User, Depends(require_permission("business:manage"))]
) -> ReviewOut:
    return await service.reply(db, user, review_id, body)
