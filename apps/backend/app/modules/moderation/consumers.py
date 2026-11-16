"""Applies moderator removals through the owning module's service (moderation never writes other tables)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, consumer


@consumer("moderation.remove_content", name="moderation.apply_removal")
async def apply_removal(db: AsyncSession, e: Event) -> None:
    from app.modules.posts import service as posts

    target = uuid.UUID(e.payload["target_id"])
    if e.payload["target_type"] == "post":
        await posts.remove_by_moderator(db, target)
    elif e.payload["target_type"] == "comment":
        await posts.remove_comment_by_moderator(db, target)
