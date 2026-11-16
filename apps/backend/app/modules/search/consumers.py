"""Keep the search index in sync from outbox events. Chat events are deliberately not consumed (DMs are never indexed)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, consumer
from app.modules.search import service as search


@consumer("posts.published", name="search.index_post")
async def index_post(db: AsyncSession, e: Event) -> None:
    from app.modules.posts import service as posts
    from app.modules.social import service as social

    rows = await posts.get_posts(db, [uuid.UUID(e.payload["post_id"])])
    if not rows or not rows[0].caption:
        return
    p = rows[0]
    public = p.visibility == "public" and not await social.is_private(db, p.author_id)
    await search.index_document(
        db,
        kind="post",
        source_id=str(p.id),
        owner_id=p.author_id,
        visibility="public" if public else "followers",
        title=e.payload.get("author_name", "Post"),
        content=p.caption or "",
    )


@consumer("posts.deleted", name="search.remove_post")
async def remove_post(db: AsyncSession, e: Event) -> None:
    await search.remove_document(db, "post", e.payload["post_id"])


@consumer("business.created", name="search.index_business_created")
async def index_business_created(db: AsyncSession, e: Event) -> None:
    await _index_business(db, uuid.UUID(e.payload["business_id"]))


@consumer("business.updated", name="search.index_business_updated")
async def index_business_updated(db: AsyncSession, e: Event) -> None:
    await _index_business(db, uuid.UUID(e.payload["business_id"]))


async def _index_business(db: AsyncSession, business_id: uuid.UUID) -> None:
    from app.modules.business import repository as business_repo

    b = await business_repo.get(db, business_id)
    if b is None:
        return
    content = " · ".join(x for x in (b.tagline, b.description, b.category.replace("_", " "), b.area, b.city) if x)
    await search.index_document(
        db,
        kind="business",
        source_id=b.slug,
        owner_id=b.owner_id,
        visibility="public" if b.status == "active" else "private",
        title=b.name,
        content=content,
    )
