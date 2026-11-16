import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, Client, CurrentUser, require_permission
from app.modules.accounts.models import User
from app.modules.business import service
from app.modules.business.models import CATEGORIES
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

router = APIRouter(prefix="/businesses", tags=["business"])


@router.post("", response_model=BusinessOwnerView, status_code=201)
async def create_business(
    body: BusinessCreate, db: DB, client: Client, user: Annotated[User, Depends(require_permission("business:create"))]
) -> BusinessOwnerView:
    return await service.create(db, user, body, client.ip)


@router.get("/mine", response_model=list[BusinessOwnerView])
async def my_businesses(db: DB, user: CurrentUser) -> list[BusinessOwnerView]:
    return await service.mine(db, user)


@router.get("/nearby", response_model=list[NearbyItem])
async def nearby(
    db: DB,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
    radius_km: Annotated[float, Query(gt=0, le=50)] = 10,
    category: Annotated[str | None, Query(pattern="^(" + "|".join(CATEGORIES) + ")$")] = None,
) -> list[NearbyItem]:
    return await service.nearby(db, lat=lat, lng=lng, radius_km=radius_km, category=category)


@router.get("/by-slug/{slug}", response_model=BusinessPublic)
async def public_page(slug: str, db: DB) -> BusinessPublic:
    return await service.public_by_slug(db, slug)


@router.patch("/{business_id}", response_model=BusinessOwnerView)
async def update_business(
    business_id: uuid.UUID,
    body: BusinessUpdate,
    db: DB,
    client: Client,
    user: Annotated[User, Depends(require_permission("business:manage"))],
) -> BusinessOwnerView:
    return await service.update(db, user, business_id, body, client.ip)


@router.post("/{business_id}/services", response_model=ServiceOut, status_code=201)
async def add_service(
    business_id: uuid.UUID, body: ServiceIn, db: DB, user: Annotated[User, Depends(require_permission("business:manage"))]
) -> ServiceOut:
    return await service.add_service(db, user, business_id, body)


@router.put("/{business_id}/services/{service_id}", response_model=ServiceOut)
async def update_service(
    business_id: uuid.UUID,
    service_id: uuid.UUID,
    body: ServiceIn,
    db: DB,
    user: Annotated[User, Depends(require_permission("business:manage"))],
) -> ServiceOut:
    return await service.update_service(db, user, business_id, service_id, body)


@router.put("/{business_id}/hours", response_model=list[HoursOut])
async def set_hours(
    business_id: uuid.UUID, body: list[HoursIn], db: DB, user: Annotated[User, Depends(require_permission("business:manage"))]
) -> list[HoursOut]:
    return await service.set_hours(db, user, business_id, body)


@router.post("/{business_id}/resources", response_model=ResourceOut, status_code=201)
async def add_resource(
    business_id: uuid.UUID, body: ResourceIn, db: DB, user: Annotated[User, Depends(require_permission("business:manage"))]
) -> ResourceOut:
    return await service.add_resource(db, user, business_id, body)
