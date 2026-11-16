import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BookingStatus = Literal["pending", "confirmed", "done", "cancelled", "expired"]


class SlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
    free_resources: int


class SlotsOut(BaseModel):
    date: date
    timezone: str
    service_id: uuid.UUID
    slots: list[SlotOut]


class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: uuid.UUID
    service_id: uuid.UUID
    starts_at: datetime
    resource_id: uuid.UUID | None = None
    customer_note: str | None = Field(default=None, max_length=500)


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    service_id: uuid.UUID
    resource_id: uuid.UUID
    customer_id: uuid.UUID
    service_name: str
    starts_at: datetime
    ends_at: datetime
    status: BookingStatus
    price_paise: int
    customer_note: str | None
    created_at: datetime


class BookingPage(BaseModel):
    items: list[BookingOut]
    next_cursor: str | None
