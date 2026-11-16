import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field

from app.api.deps import DB, CurrentUser, require_permission
from app.modules.accounts.models import User
from app.modules.events import service
from app.modules.events.service import EventBookingIn, EventBookingOut, HoldOut, PackageIn, PackageOut, VendorOut

router = APIRouter(tags=["events"])
Manager = Annotated[User, Depends(require_permission("business:manage"))]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=80)]


class InviteIn(BaseModel):
    vendor_slug: str = Field(min_length=3, max_length=60)
    terms: str | None = Field(default=None, max_length=500)


class StatusIn(BaseModel):
    status: str = Field(pattern="^(confirmed|cancelled|done)$")


@router.get("/businesses/{business_id}/packages", response_model=list[PackageOut])
async def packages(business_id: uuid.UUID, db: DB) -> list[PackageOut]:
    return await service.packages(db, business_id)


@router.post("/businesses/{business_id}/packages", response_model=PackageOut, status_code=201)
async def create_package(business_id: uuid.UUID, body: PackageIn, db: DB, user: Manager) -> PackageOut:
    return await service.create_package(db, user, business_id, body)


@router.post("/businesses/{business_id}/vendors", response_model=VendorOut, status_code=201)
async def invite_vendor(business_id: uuid.UUID, body: InviteIn, db: DB, user: Manager) -> VendorOut:
    return await service.invite_vendor(db, user, business_id, body.vendor_slug, body.terms)


@router.get("/businesses/{business_id}/vendors", response_model=list[VendorOut])
async def vendors(business_id: uuid.UUID, db: DB, user: Manager) -> list[VendorOut]:
    return await service.vendor_links(db, user, business_id)


@router.post("/businesses/{business_id}/vendor-invites/{organizer_slug}/{decision}", response_model=VendorOut)
async def answer_invite(business_id: uuid.UUID, organizer_slug: str, decision: str, db: DB, user: Manager) -> VendorOut:
    return await service.answer_invite(db, user, business_id, organizer_slug, accept=decision == "accept")


@router.post("/event-bookings", response_model=EventBookingOut, status_code=201)
async def book(
    body: EventBookingIn,
    response: Response,
    db: DB,
    key: IdempotencyKey,
    user: Annotated[User, Depends(require_permission("booking:create"))],
) -> EventBookingOut:
    out, created = await service.book(db, user, body, key)
    if not created:
        response.status_code = 200
    return out


@router.get("/event-bookings/mine", response_model=list[EventBookingOut])
async def mine(db: DB, user: CurrentUser) -> list[EventBookingOut]:
    return await service.my_event_bookings(db, user)


@router.post("/event-bookings/{eb_id}/status", response_model=EventBookingOut)
async def set_status(eb_id: uuid.UUID, body: StatusIn, db: DB, user: CurrentUser) -> EventBookingOut:
    return await service.set_status(db, user, eb_id, body.status)


@router.get("/businesses/{business_id}/event-bookings", response_model=list[EventBookingOut])
async def organizer_bookings(business_id: uuid.UUID, db: DB, user: Manager) -> list[EventBookingOut]:
    return await service.organizer_bookings(db, user, business_id)


@router.get("/businesses/{business_id}/calendar", response_model=list[HoldOut])
async def calendar(
    business_id: uuid.UUID, db: DB, user: Manager, start: date, days: Annotated[int, Query(ge=1, le=92)] = 31
) -> list[HoldOut]:
    return await service.calendar(db, user, business_id, start, days)
