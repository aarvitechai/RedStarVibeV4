"""Mounts every module router under /api/v1. New modules are included here."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

api_router = APIRouter(prefix="/api/v1")


class MetaResponse(BaseModel):
    name: str
    env: str
    version: str
    ai_provider: str


@api_router.get("/meta", response_model=MetaResponse, tags=["meta"])
async def meta() -> MetaResponse:
    s = get_settings()
    return MetaResponse(name=s.app_name, env=s.env, version="0.1.0", ai_provider=s.ai_provider)


# Module routers (one line per module).
from app.modules.accounts.router import router as accounts_router  # noqa: E402
from app.modules.admin.router import router as admin_router  # noqa: E402
from app.modules.albums.router import router as albums_router  # noqa: E402
from app.modules.booking.router import router as booking_router  # noqa: E402
from app.modules.business.router import router as business_router  # noqa: E402
from app.modules.cards.router import router as cards_router  # noqa: E402
from app.modules.chat.router import router as chat_router  # noqa: E402
from app.modules.events.router import router as events_router  # noqa: E402
from app.modules.media.router import router as media_router  # noqa: E402
from app.modules.moderation.router import router as moderation_router  # noqa: E402
from app.modules.notifications.router import router as notifications_router  # noqa: E402
from app.modules.posts.router import router as posts_router  # noqa: E402
from app.modules.referrals.router import router as referrals_router  # noqa: E402
from app.modules.reviews.router import router as reviews_router  # noqa: E402
from app.modules.shop.router import router as shop_router  # noqa: E402
from app.modules.social.router import router as social_router  # noqa: E402
from app.modules.stories.router import router as stories_router  # noqa: E402

for _r in (
    accounts_router,
    admin_router,
    business_router,
    booking_router,
    reviews_router,
    notifications_router,
    media_router,
    cards_router,
    referrals_router,
    albums_router,
    social_router,
    posts_router,
    stories_router,
    chat_router,
    moderation_router,
    events_router,
    shop_router,
):
    api_router.include_router(_r)
