"""Albums (flipbook in the browser, no server work) and slideshow MP4 export (FFmpeg, only when asked)."""

import asyncio
import secrets
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFound
from app.core.events import emit
from app.core.storage import get_storage
from app.modules.accounts.models import User
from app.modules.albums.models import Album, AlbumItem
from app.modules.media import service as media
from app.modules.media.processing import ffmpeg_available

MAX_ITEMS = 60
SECONDS_PER_PHOTO = 3


class AlbumCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    visibility: Literal["private", "link"] = "link"


class AlbumItemsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_ITEMS)


class AlbumPage(BaseModel):
    url: str
    caption: str | None


class AlbumOut(BaseModel):
    id: uuid.UUID
    title: str
    visibility: str
    share_token: str | None
    pages: list[AlbumPage]
    slideshow_status: str
    slideshow_url: str | None


async def _view(db: AsyncSession, a: Album, owner: bool) -> AlbumOut:
    items = (await db.scalars(select(AlbumItem).where(AlbumItem.album_id == a.id).order_by(AlbumItem.position))).all()
    assets = await media.public_views(db, [i.asset_id for i in items])
    pages = []
    for i in items:
        v = assets.get(i.asset_id)
        if v:
            page_url = v.urls.get("1080.webp") or v.urls.get("640.webp") or next(iter(v.urls.values()), "")
            pages.append(AlbumPage(url=page_url, caption=i.caption))
    url = get_storage().public_url(a.slideshow_key) if a.slideshow_key else None
    return AlbumOut(
        id=a.id,
        title=a.title,
        visibility=a.visibility,
        share_token=a.share_token if owner else None,
        pages=pages,
        slideshow_status=a.slideshow_status,
        slideshow_url=url,
    )


async def _owned(db: AsyncSession, user: User, album_id: uuid.UUID) -> Album:
    a = await db.get(Album, album_id)
    if a is None or a.owner_id != user.id:
        raise NotFound("album_not_found", "Album not found.")
    return a


async def create(db: AsyncSession, user: User, data: AlbumCreate) -> AlbumOut:
    a = Album(owner_id=user.id, title=data.title, visibility=data.visibility, share_token=secrets.token_urlsafe(16))
    db.add(a)
    await db.commit()
    return await _view(db, a, owner=True)


async def set_items(db: AsyncSession, user: User, album_id: uuid.UUID, data: AlbumItemsIn) -> AlbumOut:
    a = await _owned(db, user, album_id)
    assets = await media.ready_assets(db, user.id, data.asset_ids)
    if any(x.kind != "image" for x in assets):
        raise AppError("images_only", "Albums can contain photos only.")
    await db.execute(delete(AlbumItem).where(AlbumItem.album_id == a.id))
    db.add_all(AlbumItem(album_id=a.id, asset_id=aid, position=i) for i, aid in enumerate(dict.fromkeys(data.asset_ids)))
    a.slideshow_status, a.slideshow_key = "none", None
    await db.commit()
    return await _view(db, a, owner=True)


async def mine(db: AsyncSession, user: User) -> list[AlbumOut]:
    rows = (await db.scalars(select(Album).where(Album.owner_id == user.id).order_by(Album.created_at.desc()))).all()
    return [await _view(db, a, owner=True) for a in rows]


async def by_token(db: AsyncSession, token: str) -> AlbumOut:
    a = await db.scalar(select(Album).where(Album.share_token == token))
    if a is None or a.visibility == "private":
        raise NotFound("album_not_found", "Album not found.")
    return await _view(db, a, owner=False)


async def request_slideshow(db: AsyncSession, user: User, album_id: uuid.UUID) -> AlbumOut:
    a = await _owned(db, user, album_id)
    if a.slideshow_status in ("ready", "rendering"):
        return await _view(db, a, owner=True)
    count = len((await db.scalars(select(AlbumItem.asset_id).where(AlbumItem.album_id == a.id))).all())
    if count < 2:
        raise AppError("too_few_photos", "Add at least two photos to make a slideshow.")
    a.slideshow_status = "rendering"
    emit(db, "albums.slideshow_requested", {"album_id": str(a.id)})
    await db.commit()
    return await _view(db, a, owner=True)


async def render_slideshow(db: AsyncSession, album_id: uuid.UUID) -> str:
    a = await db.get(Album, album_id, with_for_update=True)
    if a is None or a.slideshow_status != "rendering":
        return a.slideshow_status if a else "missing"
    if not ffmpeg_available():
        a.slideshow_status = "failed"
        await db.commit()
        return "failed"
    items = (await db.scalars(select(AlbumItem).where(AlbumItem.album_id == a.id).order_by(AlbumItem.position))).all()
    keys = await media.variant_keys(db, [i.asset_id for i in items])
    storage = get_storage()
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for n, item in enumerate(items):
            variants = keys.get(item.asset_id, {})
            key = variants.get("1080.webp") or variants.get("640.webp")
            if not key:
                continue
            p = Path(tmp) / f"{n:03d}.webp"
            p.write_bytes(storage.get_bytes(storage.public_bucket, key, 20 * 1024 * 1024))
            paths.append(p)
        if len(paths) < 2:
            a.slideshow_status = "failed"
            await db.commit()
            return "failed"
        listing = Path(tmp) / "list.txt"
        listing.write_text(
            "".join(f"file '{p.name}'\nduration {SECONDS_PER_PHOTO}\n" for p in paths) + f"file '{paths[-1].name}'\n"
        )
        out = Path(tmp) / "slideshow.mp4"
        # Square 1080x1080, padded; silent (licensed music only, none bundled yet — Blueprint 9.7).
        await asyncio.to_thread(
            subprocess.run,
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-vf",
                "scale=1080:1080:force_original_aspect_ratio=decrease,"
                "pad=1080:1080:(ow-iw)/2:(oh-ih)/2:color=0x111111,format=yuv420p,fps=30",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "24",
                "-movflags",
                "+faststart",
                str(out),
            ],
            check=True,
            timeout=600,
            cwd=tmp,
        )
        key = f"albums/{a.id}/slideshow-{secrets.token_hex(6)}.mp4"
        storage.put_bytes(storage.public_bucket, key, out.read_bytes(), "video/mp4")
    a.slideshow_key, a.slideshow_status = key, "ready"
    await db.commit()
    return "ready"
