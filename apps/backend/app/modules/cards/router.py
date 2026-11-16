import uuid
from typing import Annotated

import segno
from fastapi import APIRouter, Query, Response

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.accounts.schemas import OkOut
from app.modules.business import service as business
from app.modules.cards import service
from app.modules.cards.render import render_share_image
from app.modules.cards.service import CardCreate, CardOut, TemplateOut

router = APIRouter(tags=["cards"])


@router.get("/cards/templates", response_model=list[TemplateOut])
async def templates(db: DB) -> list[TemplateOut]:
    return await service.templates(db)


@router.post("/cards", response_model=CardOut, status_code=201)
async def create_card(body: CardCreate, db: DB, user: CurrentUser) -> CardOut:
    return await service.create(db, user, body)


@router.get("/cards/mine", response_model=list[CardOut])
async def my_cards(db: DB, user: CurrentUser) -> list[CardOut]:
    return await service.mine(db, user)


@router.get("/cards/{card_id}", response_model=CardOut)
async def get_card(card_id: uuid.UUID, db: DB) -> CardOut:
    """Public by unguessable id, so a shared link works without login."""
    return await service.get_public(db, card_id)


@router.post("/cards/{card_id}/shared", response_model=OkOut)
async def card_shared(card_id: uuid.UUID, db: DB) -> OkOut:
    await service.record_share(db, card_id)
    return OkOut()


@router.get("/og/business/{slug}.png", response_class=Response, responses={200: {"content": {"image/png": {}}}})
async def business_share_image(slug: str, db: DB) -> Response:
    b = await business.public_by_slug(db, slug)
    subtitle = b.tagline or " · ".join(x for x in (b.category.replace("_", " ").title(), b.area, b.city) if x)
    png = render_share_image(b.name, subtitle, f"redstarvibe.com/business/{b.slug}")
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/qr.svg", response_class=Response, responses={200: {"content": {"image/svg+xml": {}}}})
async def qr(path: Annotated[str, Query(min_length=1, max_length=200)]) -> Response:
    """QR codes only for our own pages, so the endpoint cannot be used to brand arbitrary links."""
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        raise AppError("invalid_path", "QR codes can only point to RedStarVibe pages.")
    url = get_settings().public_base_url.rstrip("/") + path
    svg = segno.make(url, error="m").svg_inline(scale=8, dark="#111111", light="#ffffff")
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})
