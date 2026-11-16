"""Media: presigned upload intents, completion, async processing, and a service interface for other modules."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.errors import AppError, NotFound
from app.core.events import emit
from app.core.storage import TooLarge, get_storage
from app.modules.accounts.models import User
from app.modules.media.models import Asset
from app.modules.media.processing import InvalidMedia, process_av, process_image

log = logging.getLogger("rsv.media")

Kind = Literal["image", "video", "audio"]
Purpose = Literal["post", "story", "reel", "card", "album", "avatar", "business", "product", "voice"]
LIMITS: dict[str, tuple[int, frozenset[str]]] = {
    "image": (20 * 1024 * 1024, frozenset({"image/jpeg", "image/png", "image/webp", "image/avif", "image/gif"})),
    "video": (200 * 1024 * 1024, frozenset({"video/mp4", "video/quicktime", "video/webm"})),
    "audio": (10 * 1024 * 1024, frozenset({"audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac"})),
}
MAX_DURATION = {"reel": 90.0, "story": 60.0, "voice": 300.0}
DEFAULT_MAX_DURATION = 600.0  # post video: 10 minutes


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    purpose: Purpose = "post"
    content_type: str = Field(max_length=60)
    size_bytes: int = Field(gt=0)


class UploadIntent(BaseModel):
    asset_id: uuid.UUID
    upload_url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expires_in_s: int = 600


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    status: str
    width: int | None
    height: int | None
    duration_s: float | None
    urls: dict[str, str]
    error: str | None


def to_out(a: Asset) -> AssetOut:
    storage = get_storage()
    urls = {name: storage.public_url(key) for name, key in (a.variants or {}).items()}
    return AssetOut(
        id=a.id, kind=a.kind, status=a.status, width=a.width, height=a.height, duration_s=a.duration_s, urls=urls, error=a.error
    )


async def create_upload(db: AsyncSession, user: User, req: UploadRequest) -> UploadIntent:
    max_bytes, types = LIMITS[req.kind]
    if req.content_type not in types:
        raise AppError("unsupported_type", f"This file type is not allowed for {req.kind}.")
    if req.size_bytes > max_bytes:
        raise AppError("file_too_large", f"Files must be under {max_bytes // (1024 * 1024)} MB.")
    await rate_limit.enforce("upload_url", str(user.id), limit=60, window_s=3600)
    asset_id = uuid.uuid4()
    key = f"users/{user.id}/{asset_id}"
    db.add(
        Asset(
            id=asset_id,
            owner_id=user.id,
            kind=req.kind,
            purpose=req.purpose,
            status="pending",
            raw_key=key,
            content_type=req.content_type,
            size_bytes=req.size_bytes,
        )
    )
    await db.commit()
    url = get_storage().presign_put(key, req.content_type, max_bytes)
    return UploadIntent(asset_id=asset_id, upload_url=url, headers={"Content-Type": req.content_type})


async def complete_upload(db: AsyncSession, user: User, asset_id: uuid.UUID) -> AssetOut:
    a = await db.get(Asset, asset_id)
    if a is None or a.owner_id != user.id:
        raise NotFound("asset_not_found", "File not found.")
    if a.status == "pending":
        a.status = "processing"
        emit(db, "media.uploaded", {"asset_id": str(a.id), "owner_id": str(a.owner_id), "kind": a.kind})
        await db.commit()
    return to_out(a)


async def get_owned(db: AsyncSession, user: User, asset_id: uuid.UUID) -> AssetOut:
    a = await db.get(Asset, asset_id)
    if a is None or a.owner_id != user.id:
        raise NotFound("asset_not_found", "File not found.")
    return to_out(a)


async def process(db: AsyncSession, asset_id: uuid.UUID) -> str:
    """Worker step. Idempotent: a ready/failed asset is left alone."""
    a = await db.get(Asset, asset_id, with_for_update=True)
    if a is None or a.status in ("ready", "failed"):
        return a.status if a else "missing"
    storage = get_storage()
    max_bytes = LIMITS[a.kind][0]
    try:
        data = storage.get_bytes(storage.raw_bucket, a.raw_key, max_bytes)
        if len(data) > max_bytes:
            raise TooLarge(a.raw_key)
        if a.kind == "image":
            result = process_image(data)
        else:
            result = process_av(data, a.kind, MAX_DURATION.get(a.purpose, DEFAULT_MAX_DURATION))
    except (InvalidMedia, TooLarge, KeyError) as exc:
        a.status, a.error = "failed", str(exc)[:200] or "invalid file"
        await db.commit()
        return a.status
    variants: dict[str, Any] = {}
    for r in result.renditions:
        key = f"media/{a.id}/{r.name}"
        storage.put_bytes(storage.public_bucket, key, r.data, r.content_type)
        variants[r.name] = key
    a.variants, a.width, a.height, a.duration_s = variants, result.width, result.height, result.duration_s
    a.status, a.processed_at = "ready", datetime.now(UTC)
    try:
        storage.delete(storage.raw_bucket, a.raw_key)  # raw upload (with original metadata) is not kept
    except Exception:
        log.warning("raw_delete_failed asset=%s", a.id)
    emit(db, "media.ready", {"asset_id": str(a.id), "owner_id": str(a.owner_id), "kind": a.kind})
    await db.commit()
    return a.status


# --- Interface for other modules ---


async def ready_assets(db: AsyncSession, owner_id: uuid.UUID, ids: list[uuid.UUID]) -> list[AssetOut]:
    """Return the caller's ready assets in the given order; raises if any id is not theirs or not ready."""
    if not ids:
        return []
    rows = {a.id: a for a in (await db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.owner_id == owner_id))).all()}
    out = []
    for i in ids:
        a = rows.get(i)
        if a is None:
            raise NotFound("asset_not_found", "One of the files was not found.")
        if a.status != "ready":
            raise AppError("asset_not_ready", "A file is still processing. Try again in a moment.")
        out.append(to_out(a))
    return out


async def public_views(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, AssetOut]:
    if not ids:
        return {}
    rows = (await db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.status == "ready"))).all()
    return {a.id: to_out(a) for a in rows}


async def variant_keys(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, str]]:
    """Object keys of ready renditions, for worker jobs that read media (slideshows, cards)."""
    if not ids:
        return {}
    rows = (await db.scalars(select(Asset).where(Asset.id.in_(ids), Asset.status == "ready"))).all()
    return {a.id: dict(a.variants) for a in rows}
