import re
import uuid
from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.naming import normalize_handle
from app.modules.business.models import CATEGORIES

Category = Literal[CATEGORIES]  # type: ignore[valid-type]
_PHONE_RE = re.compile(r"^\+?[0-9 ]{10,15}$")


def _clean_phone(v: str | None) -> str | None:
    if v is None or not v.strip():
        return None
    if not _PHONE_RE.fullmatch(v.strip()):
        raise ValueError("Enter a valid phone number.")
    return v.replace(" ", "")


class BusinessCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str = Field(min_length=2, max_length=120)
    category: Category
    tagline: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    phone: str | None = None
    area: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=80)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    service_radius_km: int = Field(default=10, ge=1, le=200)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        return normalize_handle(v, max_len=60)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return _clean_phone(v)

    @model_validator(mode="after")
    def _both_coords(self) -> "BusinessCreate":
        if (self.lat is None) != (self.lng is None):
            raise ValueError("Give both latitude and longitude, or neither.")
        return self


class BusinessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=120)
    category: Category | None = None
    tagline: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    phone: str | None = None
    area: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=80)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    service_radius_km: int | None = Field(default=None, ge=1, le=200)
    status: Literal["active", "hidden"] | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return _clean_phone(v)


class ServiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    price_paise: int = Field(ge=0, le=100_000_000, description="Integer paise; ₹499 = 49900")
    duration_min: int = Field(ge=5, le=720)
    buffer_min: int = Field(default=0, ge=0, le=240)
    active: bool = True


class ServiceOut(ServiceIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class HoursIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    opens: time
    closes: time

    @model_validator(mode="after")
    def _order(self) -> "HoursIn":
        if self.opens >= self.closes:
            raise ValueError("Closing time must be after opening time.")
        return self


class HoursOut(HoursIn):
    model_config = ConfigDict(from_attributes=True)


class ResourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    active: bool = True


class ResourceOut(ResourceIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class BusinessPublic(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    category: str
    tagline: str | None
    description: str | None
    area: str | None
    city: str | None
    lat: float | None
    lng: float | None
    timezone: str
    services: list[ServiceOut]
    hours: list[HoursOut]


class BusinessOwnerView(BusinessPublic):
    owner_id: uuid.UUID
    phone: str | None
    status: str
    service_radius_km: int
    resources: list[ResourceOut]
    created_at: datetime


class NearbyItem(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    category: str
    tagline: str | None
    area: str | None
    distance_km: float
