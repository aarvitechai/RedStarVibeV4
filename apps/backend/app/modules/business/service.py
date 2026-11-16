"""Business pages, services, hours and bookable resources. Owner checks happen here, not in the router."""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.errors import AppError, Conflict, NotFound
from app.core.events import emit
from app.core.ids import uuid7
from app.core.permissions import has_permission
from app.modules.accounts import service as accounts
from app.modules.accounts.models import User
from app.modules.audit import service as audit
from app.modules.business import repository as repo
from app.modules.business.models import Business, BusinessHours, Resource, Service
from app.modules.business.schemas import (
    BusinessCreate,
    BusinessOwnerView,
    BusinessPublic,
    BusinessUpdate,
    HoursIn,
    HoursOut,
    NearbyItem,
    ResourceIn,
    ResourceOut,
    ServiceIn,
    ServiceOut,
)

MAX_BUSINESSES_PER_OWNER = 5


async def owned(db: AsyncSession, business_id: uuid.UUID, user: User) -> Business:
    """Return the business only if `user` owns it (or is a superadmin). Otherwise 404, so ids are not probed."""
    business = await repo.get(db, business_id)
    if business is None or (business.owner_id != user.id and not has_permission(user.role, "*")):
        raise NotFound("business_not_found", "Business not found.")
    return business


async def public_by_slug(db: AsyncSession, slug: str) -> BusinessPublic:
    business = await repo.get_by_slug(db, slug)
    if business is None or business.status != "active":
        raise NotFound("business_not_found", "Business not found.")
    return await _public(db, business)


async def _public(db: AsyncSession, b: Business) -> BusinessPublic:
    return BusinessPublic(
        id=b.id,
        slug=b.slug,
        name=b.name,
        category=b.category,
        tagline=b.tagline,
        description=b.description,
        area=b.area,
        city=b.city,
        lat=b.lat,
        lng=b.lng,
        timezone=b.timezone,
        services=[ServiceOut.model_validate(s) for s in await repo.services(db, b.id, active_only=True)],
        hours=[HoursOut.model_validate(h) for h in await repo.hours(db, b.id)],
    )


async def owner_view(db: AsyncSession, b: Business) -> BusinessOwnerView:
    pub = await _public(db, b)
    return BusinessOwnerView(
        **pub.model_dump(exclude={"services"}),
        services=[ServiceOut.model_validate(s) for s in await repo.services(db, b.id, active_only=False)],
        owner_id=b.owner_id,
        phone=crypto.decrypt(b.phone_enc),
        status=b.status,
        service_radius_km=b.service_radius_km,
        created_at=b.created_at,
        resources=[ResourceOut.model_validate(r) for r in await repo.resources(db, b.id, active_only=False)],
    )


async def create(db: AsyncSession, user: User, data: BusinessCreate, ip: str) -> BusinessOwnerView:
    if len(await repo.list_owned(db, user.id)) >= MAX_BUSINESSES_PER_OWNER:
        raise Conflict("business_limit", f"You can create up to {MAX_BUSINESSES_PER_OWNER} businesses.")
    if await repo.slug_taken(db, data.slug):
        raise Conflict("slug_taken", "This page address is already taken.")
    business = Business(
        id=uuid7(),
        owner_id=user.id,
        slug=data.slug,
        name=data.name,
        category=data.category,
        tagline=data.tagline,
        description=data.description,
        phone_enc=crypto.encrypt(data.phone),
        area=data.area,
        city=data.city,
        lat=data.lat,
        lng=data.lng,
        service_radius_km=data.service_radius_km,
    )
    db.add(business)
    # Every business starts with one bookable resource (the owner) so bookings work immediately.
    db.add(Resource(business_id=business.id, name="Owner"))
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict("slug_taken", "This page address is already taken.") from exc
    await accounts.ensure_business_role(db, user)
    emit(db, "business.created", {"business_id": str(business.id), "owner_id": str(user.id), "slug": business.slug})
    await audit.record(db, actor_id=user.id, action="business.created", target_type="business", target_id=str(business.id), ip=ip)
    await db.commit()
    return await owner_view(db, business)


async def update(db: AsyncSession, user: User, business_id: uuid.UUID, data: BusinessUpdate, ip: str) -> BusinessOwnerView:
    b = await owned(db, business_id, user)
    changes = data.model_dump(exclude_unset=True)
    if "phone" in changes:
        b.phone_enc = crypto.encrypt(changes.pop("phone"))
    lat, lng = changes.get("lat", b.lat), changes.get("lng", b.lng)
    if (lat is None) != (lng is None):
        raise AppError("location_incomplete", "Give both latitude and longitude, or neither.")
    for field, value in changes.items():
        setattr(b, field, value)
    await audit.record(
        db,
        actor_id=user.id,
        action="business.updated",
        target_type="business",
        target_id=str(b.id),
        ip=ip,
        details={"fields": sorted(data.model_dump(exclude_unset=True))},
    )
    await db.commit()
    await db.refresh(b)
    return await owner_view(db, b)


async def mine(db: AsyncSession, user: User) -> list[BusinessOwnerView]:
    return [await owner_view(db, b) for b in await repo.list_owned(db, user.id)]


async def add_service(db: AsyncSession, user: User, business_id: uuid.UUID, data: ServiceIn) -> ServiceOut:
    b = await owned(db, business_id, user)
    service = Service(business_id=b.id, **data.model_dump())
    db.add(service)
    await db.commit()
    return ServiceOut.model_validate(service)


async def update_service(
    db: AsyncSession, user: User, business_id: uuid.UUID, service_id: uuid.UUID, data: ServiceIn
) -> ServiceOut:
    b = await owned(db, business_id, user)
    service = await repo.get_service(db, b.id, service_id)
    if service is None:
        raise NotFound("service_not_found", "Service not found.")
    for field, value in data.model_dump().items():
        setattr(service, field, value)
    await db.commit()
    return ServiceOut.model_validate(service)


async def set_hours(db: AsyncSession, user: User, business_id: uuid.UUID, rows: list[HoursIn]) -> list[HoursOut]:
    b = await owned(db, business_id, user)
    by_day: dict[int, list[HoursIn]] = {}
    for r in sorted(rows, key=lambda r: (r.weekday, r.opens)):
        day = by_day.setdefault(r.weekday, [])
        if day and day[-1].closes > r.opens:
            raise AppError("hours_overlap", "Opening hours on the same day overlap.")
        day.append(r)
    await repo.replace_hours(db, b.id, [BusinessHours(business_id=b.id, **r.model_dump()) for r in rows])
    await db.commit()
    return [HoursOut.model_validate(h) for h in await repo.hours(db, b.id)]


async def add_resource(db: AsyncSession, user: User, business_id: uuid.UUID, data: ResourceIn) -> ResourceOut:
    b = await owned(db, business_id, user)
    resource = Resource(business_id=b.id, **data.model_dump())
    db.add(resource)
    await db.commit()
    return ResourceOut.model_validate(resource)


async def nearby(db: AsyncSession, *, lat: float, lng: float, radius_km: float, category: str | None) -> list[NearbyItem]:
    rows = await repo.nearby(db, lat=lat, lng=lng, radius_km=radius_km, category=category, limit=50)
    return [NearbyItem.model_validate(r) for r in rows]


# --- Service interface for other modules (booking, reviews). They never read business tables directly. ---


async def get_active_business(db: AsyncSession, business_id: uuid.UUID) -> Business:
    b = await repo.get(db, business_id)
    if b is None or b.status != "active":
        raise NotFound("business_not_found", "Business not found.")
    return b


async def get_bookable_service(db: AsyncSession, business_id: uuid.UUID, service_id: uuid.UUID) -> Service:
    s = await repo.get_service(db, business_id, service_id)
    if s is None or not s.active:
        raise NotFound("service_not_found", "Service not found.")
    return s


async def opening_hours(db: AsyncSession, business_id: uuid.UUID) -> list[BusinessHours]:
    return list(await repo.hours(db, business_id))


async def active_resource_ids(db: AsyncSession, business_id: uuid.UUID) -> list[uuid.UUID]:
    return [r.id for r in await repo.resources(db, business_id, active_only=True)]
