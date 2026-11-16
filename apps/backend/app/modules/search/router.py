"""Search and AI features. AI suggests; the user always reviews and decides (Blueprint 20.7)."""

import re
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.ai import gateway
from app.ai.providers import AIUnavailable, get_ai, rule_hashtags
from app.api.deps import DB, CurrentUser, optional_user
from app.core.errors import AppError
from app.core.storage import get_storage
from app.modules.media import service as media
from app.modules.payments import service as payments
from app.modules.search import service
from app.modules.search.service import AnswerOut, AskIn, SearchHit

router = APIRouter(tags=["search", "ai"])


class CaptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = Field(default=None, max_length=500)
    asset_id: uuid.UUID | None = None


class CaptionOut(BaseModel):
    caption: str
    hashtags: list[str]
    alt_text: str | None
    source: Literal["ai", "rules"]


class ListingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(max_length=40)
    notes: str | None = Field(default=None, max_length=500)


class TextOut(BaseModel):
    text: str
    source: Literal["ai", "rules", "unavailable"]


class CommentCheckIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class CommentCheckOut(BaseModel):
    warn: bool
    score: float
    message: str | None


class TranslateIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    target: Literal["en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa"]


class SubtitlesIn(BaseModel):
    asset_id: uuid.UUID


async def _limit(db: DB, user_id: uuid.UUID) -> int:
    return (await payments.entitlements(db, user_id)).ai_calls_per_day


@router.get("/search", response_model=list[SearchHit])
async def search(
    request: Request,
    db: DB,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    kind: Annotated[str | None, Query(pattern="^(post|business|help)$")] = None,
) -> list[SearchHit]:
    return await service.search(db, await optional_user(request, db), q, kinds=[kind] if kind else None)


@router.post("/ai/assistant", response_model=AnswerOut)
async def assistant(body: AskIn, db: DB, user: CurrentUser) -> AnswerOut:
    return await service.ask(db, user, body)


@router.post("/ai/caption", response_model=CaptionOut)
async def caption(body: CaptionIn, db: DB, user: CurrentUser) -> CaptionOut:
    image: bytes | None = None
    if body.asset_id:
        keys = await media.variant_keys(db, [(await media.ready_assets(db, user.id, [body.asset_id]))[0].id])
        key = keys.get(body.asset_id, {}).get("640.webp")
        if key:
            storage = get_storage()
            image = storage.get_bytes(storage.public_bucket, key, 5 * 1024 * 1024)
    version, system = gateway.prompt("caption_v1")
    notes = body.notes or ""

    async def ai() -> CaptionOut:
        alt = await get_ai().caption_image(image) if image else None
        out = await get_ai().complete(system, f"<notes>{notes}</notes>\n<photo>{alt or 'no photo'}</photo>", max_tokens=200)
        text, _, tags = out.partition("HASHTAGS:")
        found = re.findall(r"#[\wऀ-ॿ]+", tags or text)
        return CaptionOut(caption=text.strip(), hashtags=found[:6] or rule_hashtags(notes), alt_text=alt, source="ai")

    def rules() -> CaptionOut:
        return CaptionOut(caption=notes.strip(), hashtags=rule_hashtags(notes), alt_text=None, source="rules")

    result, _ = await gateway.run(db, user.id, await _limit(db, user.id), "caption", ai, rules, version)
    return result


@router.post("/ai/listing", response_model=TextOut)
async def listing(body: ListingIn, db: DB, user: CurrentUser) -> TextOut:
    version, system = gateway.prompt("listing_v1")

    async def ai() -> TextOut:
        out = await get_ai().complete(
            system, f"<item>{body.name}</item><category>{body.category}</category><notes>{body.notes or ''}</notes>"
        )
        return TextOut(text=out, source="ai")

    def rules() -> TextOut:
        return TextOut(
            text=f"{body.name} — quality {body.category.replace('_', ' ')} from a trusted local seller. {body.notes or ''}".strip(),
            source="rules",
        )

    result, _ = await gateway.run(db, user.id, await _limit(db, user.id), "listing", ai, rules, version)
    return result


@router.post("/ai/comment-check", response_model=CommentCheckOut)
async def comment_check(body: CommentCheckIn, db: DB, user: CurrentUser) -> CommentCheckOut:
    """Toxic-comment warning before posting. A nudge only: humans decide on removals (Blueprint 16.3)."""
    score = await get_ai().toxicity(body.text)
    warn = score >= 0.5
    return CommentCheckOut(
        warn=warn, score=round(score, 2), message="This might hurt someone. Do you want to rephrase it?" if warn else None
    )


@router.post("/ai/translate", response_model=TextOut)
async def translate(body: TranslateIn, db: DB, user: CurrentUser) -> TextOut:
    async def ai() -> TextOut:
        return TextOut(text=await get_ai().translate(body.text, body.target), source="ai")

    result, _ = await gateway.run(
        db, user.id, await _limit(db, user.id), "translate", ai, lambda: TextOut(text=body.text, source="unavailable")
    )
    return result


@router.post("/ai/subtitles", response_model=TextOut)
async def subtitles(body: SubtitlesIn, db: DB, user: CurrentUser) -> TextOut:
    asset = (await media.ready_assets(db, user.id, [body.asset_id]))[0]
    if asset.kind not in ("video", "audio"):
        raise AppError("not_audio", "Subtitles need a video or voice note.")
    keys = (await media.variant_keys(db, [asset.id]))[asset.id]
    key = keys.get("audio.m4a") or keys.get("video.mp4")
    storage = get_storage()

    async def ai() -> TextOut:
        if key is None:
            raise AIUnavailable("no audio")
        return TextOut(
            text=await get_ai().transcribe(storage.get_bytes(storage.public_bucket, key, 25 * 1024 * 1024)), source="ai"
        )

    result, _ = await gateway.run(
        db, user.id, await _limit(db, user.id), "subtitles", ai, lambda: TextOut(text="", source="unavailable")
    )
    return result


class HelpArticle(BaseModel):
    slug: str
    title: str
    body: str


@router.get("/help", response_model=list[HelpArticle])
async def help_articles() -> list[HelpArticle]:
    from app.ai.help_docs import HELP_DOCS

    return [HelpArticle(slug=s, title=t, body=b) for s, t, b in HELP_DOCS]
