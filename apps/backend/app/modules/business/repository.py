"""All business SQL. Every query on child tables filters by business_id."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.business.models import Business, BusinessHours, Resource, Service


async def get(db: AsyncSession, business_id: uuid.UUID) -> Business | None:
    return await db.get(Business, business_id)


async def get_by_slug(db: AsyncSession, slug: str) -> Business | None:
    return await db.scalar(select(Business).where(Business.slug == slug))


async def slug_taken(db: AsyncSession, slug: str) -> bool:
    return await db.scalar(select(Business.id).where(Business.slug == slug)) is not None


async def list_owned(db: AsyncSession, owner_id: uuid.UUID) -> Sequence[Business]:
    return (await db.scalars(select(Business).where(Business.owner_id == owner_id).order_by(Business.created_at))).all()


async def services(db: AsyncSession, business_id: uuid.UUID, *, active_only: bool) -> Sequence[Service]:
    stmt = select(Service).where(Service.business_id == business_id)
    if active_only:
        stmt = stmt.where(Service.active.is_(True))
    return (await db.scalars(stmt.order_by(Service.created_at))).all()


async def get_service(db: AsyncSession, business_id: uuid.UUID, service_id: uuid.UUID) -> Service | None:
    return await db.scalar(select(Service).where(Service.id == service_id, Service.business_id == business_id))


async def hours(db: AsyncSession, business_id: uuid.UUID) -> Sequence[BusinessHours]:
    return (
        await db.scalars(
            select(BusinessHours)
            .where(BusinessHours.business_id == business_id)
            .order_by(BusinessHours.weekday, BusinessHours.opens)
        )
    ).all()


async def replace_hours(db: AsyncSession, business_id: uuid.UUID, rows: list[BusinessHours]) -> None:
    await db.execute(delete(BusinessHours).where(BusinessHours.business_id == business_id))
    db.add_all(rows)


async def resources(db: AsyncSession, business_id: uuid.UUID, *, active_only: bool) -> Sequence[Resource]:
    stmt = select(Resource).where(Resource.business_id == business_id)
    if active_only:
        stmt = stmt.where(Resource.active.is_(True))
    return (await db.scalars(stmt.order_by(Resource.created_at))).all()


async def get_resource(db: AsyncSession, business_id: uuid.UUID, resource_id: uuid.UUID) -> Resource | None:
    return await db.scalar(select(Resource).where(Resource.id == resource_id, Resource.business_id == business_id))


_NEARBY_SQL = text("""
    SELECT id, slug, name, category, tagline, area,
           ST_Distance(location, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) / 1000.0 AS distance_km
    FROM business.businesses
    WHERE status = 'active'
      AND location IS NOT NULL
      AND ST_DWithin(location, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius_m)
      AND (CAST(:category AS text) IS NULL OR category = :category)
    ORDER BY distance_km
    LIMIT :limit
""")


async def nearby(
    db: AsyncSession, *, lat: float, lng: float, radius_km: float, category: str | None, limit: int
) -> list[dict[str, object]]:
    rows = await db.execute(
        _NEARBY_SQL, {"lat": lat, "lng": lng, "radius_m": radius_km * 1000, "category": category, "limit": limit}
    )
    return [dict(r._mapping) for r in rows]
