import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from app.api.deps import DB, CurrentUser, require_permission
from app.modules.accounts.models import User
from app.modules.booking import service
from app.modules.booking.schemas import BookingCreate, BookingOut, BookingPage, SlotsOut

router = APIRouter(tags=["booking"])

IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=80, description="Unique per booking attempt; retries reuse it")
]


@router.get("/businesses/{business_id}/slots", response_model=SlotsOut)
async def slots(business_id: uuid.UUID, service_id: uuid.UUID, day: Annotated[date, Query(alias="date")], db: DB) -> SlotsOut:
    return await service.slots(db, business_id, service_id, day)


@router.post(
    "/bookings",
    response_model=BookingOut,
    status_code=201,
    responses={200: {"model": BookingOut, "description": "Replay of an earlier request with the same key"}},
)
async def create_booking(
    body: BookingCreate,
    response: Response,
    db: DB,
    key: IdempotencyKey,
    user: Annotated[User, Depends(require_permission("booking:create"))],
) -> BookingOut:
    booking, created = await service.create(db, user, body, key)
    if not created:
        response.status_code = 200
    return booking


@router.get("/bookings/mine", response_model=BookingPage)
async def my_bookings(
    db: DB, user: CurrentUser, cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> BookingPage:
    return await service.my_bookings(db, user, cursor, limit)


@router.get("/businesses/{business_id}/bookings", response_model=list[BookingOut])
async def business_bookings(
    business_id: uuid.UUID,
    day: Annotated[date, Query(alias="date")],
    db: DB,
    user: Annotated[User, Depends(require_permission("booking:manage"))],
) -> list[BookingOut]:
    return await service.business_day(db, user, business_id, day)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
async def cancel(booking_id: uuid.UUID, db: DB, user: CurrentUser) -> BookingOut:
    return await service.transition(db, user, booking_id, "cancelled")


@router.post("/bookings/{booking_id}/confirm", response_model=BookingOut)
async def confirm(
    booking_id: uuid.UUID, db: DB, user: Annotated[User, Depends(require_permission("booking:manage"))]
) -> BookingOut:
    return await service.transition(db, user, booking_id, "confirmed")


@router.post("/bookings/{booking_id}/complete", response_model=BookingOut)
async def complete(
    booking_id: uuid.UUID, db: DB, user: Annotated[User, Depends(require_permission("booking:manage"))]
) -> BookingOut:
    return await service.transition(db, user, booking_id, "done")
