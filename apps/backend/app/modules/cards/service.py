"""Digital greeting cards: create from a template, render in the media worker (idempotent by input hash), share."""

import hashlib
import json
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.events import emit
from app.core.storage import get_storage
from app.modules.accounts.models import User
from app.modules.cards.models import Card, CardTemplate
from app.modules.cards.render import render_card
from app.modules.media import service as media
from app.modules.media.models import Asset


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    occasion: str
    name: str
    locale: str
    premium: bool
    preview: dict[str, str]


class CardFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=60)
    message: str | None = Field(default=None, max_length=280)
    sender: str | None = Field(default=None, max_length=40, alias="from")


class CardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_id: str = Field(max_length=40)
    fields: CardFields
    photo_asset_id: uuid.UUID | None = None


class CardOut(BaseModel):
    id: uuid.UUID
    template_id: str
    status: str
    image_url: str | None
    title: str
    created_at: datetime


def _out(c: Card) -> CardOut:
    url = get_storage().public_url(c.render_key) if c.render_key else None
    return CardOut(
        id=c.id,
        template_id=c.template_id,
        status=c.status,
        image_url=url,
        title=str(c.fields.get("title", "")),
        created_at=c.created_at,
    )


async def templates(db: AsyncSession) -> list[TemplateOut]:
    rows = (await db.scalars(select(CardTemplate).where(CardTemplate.active.is_(True)).order_by(CardTemplate.occasion))).all()
    return [
        TemplateOut(
            id=t.id,
            occasion=t.occasion,
            name=t.name,
            locale=t.locale,
            premium=t.premium,
            preview={"bg_top": t.spec["bg_top"], "bg_bottom": t.spec["bg_bottom"]},
        )
        for t in rows
    ]


async def create(db: AsyncSession, user: User, data: CardCreate) -> CardOut:
    tpl = await db.get(CardTemplate, data.template_id)
    if tpl is None or not tpl.active:
        raise NotFound("template_not_found", "Template not found.")
    if data.photo_asset_id:
        await media.ready_assets(db, user.id, [data.photo_asset_id])  # must be the caller's own ready image
    fields = {
        k: v for k, v in {"title": data.fields.title, "message": data.fields.message, "from": data.fields.sender}.items() if v
    }
    digest = hashlib.sha256(
        json.dumps({"t": tpl.id, "v": tpl.version, "f": fields, "p": str(data.photo_asset_id)}, sort_keys=True).encode()
    ).hexdigest()
    card = Card(owner_id=user.id, template_id=tpl.id, fields=fields, photo_asset_id=data.photo_asset_id, input_hash=digest)
    db.add(card)
    await db.flush()
    emit(db, "cards.created", {"card_id": str(card.id), "owner_id": str(user.id)})
    await db.commit()
    return _out(card)


async def get_public(db: AsyncSession, card_id: uuid.UUID) -> CardOut:
    c = await db.get(Card, card_id)
    if c is None:
        raise NotFound("card_not_found", "Card not found.")
    return _out(c)


async def mine(db: AsyncSession, user: User) -> list[CardOut]:
    rows = (await db.scalars(select(Card).where(Card.owner_id == user.id).order_by(Card.created_at.desc()).limit(50))).all()
    return [_out(c) for c in rows]


async def record_share(db: AsyncSession, card_id: uuid.UUID) -> None:
    await db.execute(update(Card).where(Card.id == card_id).values(share_count=Card.share_count + 1))
    await db.commit()


async def render(db: AsyncSession, card_id: uuid.UUID) -> str:
    """Worker step. Same inputs -> same object key, so retries and duplicates never re-render or duplicate files."""
    c = await db.get(Card, card_id, with_for_update=True)
    if c is None:
        return "missing"
    if c.status == "ready":
        return "ready"
    tpl = await db.get(CardTemplate, c.template_id)
    assert tpl is not None
    storage = get_storage()
    key = f"cards/{c.input_hash}.png"
    photo: bytes | None = None
    if c.photo_asset_id:
        a = await db.get(Asset, c.photo_asset_id)
        if a and a.status == "ready":
            best = next((k for k in ("1080.webp", "640.webp", "320.webp") if k in a.variants), None)
            if best:
                photo = storage.get_bytes(storage.public_bucket, a.variants[best], 20 * 1024 * 1024)
    png = render_card(tpl.spec, {k: str(v) for k, v in c.fields.items()}, photo)
    storage.put_bytes(storage.public_bucket, key, png, "image/png")
    c.render_key, c.status = key, "ready"
    await db.commit()
    return "ready"
