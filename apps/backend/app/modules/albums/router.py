import uuid

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.modules.albums import service
from app.modules.albums.service import AlbumCreate, AlbumItemsIn, AlbumOut

router = APIRouter(prefix="/albums", tags=["albums"])


@router.post("", response_model=AlbumOut, status_code=201)
async def create_album(body: AlbumCreate, db: DB, user: CurrentUser) -> AlbumOut:
    return await service.create(db, user, body)


@router.get("/mine", response_model=list[AlbumOut])
async def my_albums(db: DB, user: CurrentUser) -> list[AlbumOut]:
    return await service.mine(db, user)


@router.put("/{album_id}/items", response_model=AlbumOut)
async def set_items(album_id: uuid.UUID, body: AlbumItemsIn, db: DB, user: CurrentUser) -> AlbumOut:
    return await service.set_items(db, user, album_id, body)


@router.post("/{album_id}/slideshow", response_model=AlbumOut, status_code=202)
async def slideshow(album_id: uuid.UUID, db: DB, user: CurrentUser) -> AlbumOut:
    """Builds the MP4 in the media worker only when the user asks (download/share)."""
    return await service.request_slideshow(db, user, album_id)


@router.get("/shared/{token}", response_model=AlbumOut)
async def shared(token: str, db: DB) -> AlbumOut:
    return await service.by_token(db, token)
