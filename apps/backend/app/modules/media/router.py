import uuid

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.modules.media import service
from app.modules.media.service import AssetOut, UploadIntent, UploadRequest

router = APIRouter(prefix="/media", tags=["media"])


@router.post("/uploads", response_model=UploadIntent, status_code=201)
async def create_upload(body: UploadRequest, db: DB, user: CurrentUser) -> UploadIntent:
    """Step 1: get a 10-minute presigned PUT URL. The browser uploads the file straight to storage."""
    return await service.create_upload(db, user, body)


@router.post("/uploads/{asset_id}/complete", response_model=AssetOut)
async def complete_upload(asset_id: uuid.UUID, db: DB, user: CurrentUser) -> AssetOut:
    """Step 2: tell us the upload finished. Processing runs in the media worker; poll GET /media/{id}."""
    return await service.complete_upload(db, user, asset_id)


@router.get("/{asset_id}", response_model=AssetOut)
async def get_asset(asset_id: uuid.UUID, db: DB, user: CurrentUser) -> AssetOut:
    return await service.get_owned(db, user, asset_id)
