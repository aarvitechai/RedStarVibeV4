"""Feed fan-out and social notifications, driven by outbox events."""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, consumer
from app.modules.notifications.service import deliver
from app.modules.posts import feed
from app.modules.social import service as social


@consumer("posts.published", name="feed.fan_out")
async def fan_out(db: AsyncSession, e: Event) -> None:
    p = e.payload
    await feed.fan_out(db, uuid.UUID(p["post_id"]), uuid.UUID(p["author_id"]), datetime.fromisoformat(p["created_at"]))


@consumer("posts.deleted", name="feed.remove")
async def remove(db: AsyncSession, e: Event) -> None:
    author = uuid.UUID(e.payload["author_id"])
    await feed.remove(uuid.UUID(e.payload["post_id"]), author, await social.follower_ids(db, author))


@consumer("posts.published", name="notifications.post_mentions")
async def post_mentions(db: AsyncSession, e: Event) -> None:
    for uid in e.payload.get("mentioned_ids", []):
        await deliver(
            db,
            event_id=e.event_id,
            user_id=uuid.UUID(uid),
            type="post.mention",
            title=f"{e.payload['author_name']} mentioned you in a post",
            link=f"/p/{e.payload['post_id']}",
        )


@consumer("posts.liked", name="notifications.post_liked")
async def liked(db: AsyncSession, e: Event) -> None:
    p = e.payload
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(p["author_id"]),
        type="post.like",
        title=f"{p['liker_name']} liked your post",
        link=f"/p/{p['post_id']}",
    )


@consumer("posts.commented", name="notifications.post_commented")
async def commented(db: AsyncSession, e: Event) -> None:
    p = e.payload
    if p["author_id"] != p["commenter_id"]:
        await deliver(
            db,
            event_id=e.event_id,
            user_id=uuid.UUID(p["author_id"]),
            type="post.comment",
            title=f"{p['commenter_name']} commented on your post",
            link=f"/p/{p['post_id']}",
        )
    for uid in p.get("mentioned_ids", []):
        await deliver(
            db,
            event_id=e.event_id,
            user_id=uuid.UUID(uid),
            type="comment.mention",
            title=f"{p['commenter_name']} mentioned you in a comment",
            link=f"/p/{p['post_id']}",
        )


@consumer("social.followed", name="notifications.followed")
async def followed(db: AsyncSession, e: Event) -> None:
    p = e.payload
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(p["followee_id"]),
        type="social.follow",
        title=f"{p['follower_name']} started following you",
        link="/feed",
    )


@consumer("social.follow_requested", name="notifications.follow_requested")
async def follow_requested(db: AsyncSession, e: Event) -> None:
    p = e.payload
    await deliver(
        db,
        event_id=e.event_id,
        user_id=uuid.UUID(p["followee_id"]),
        type="social.follow_request",
        title=f"{p['follower_name']} wants to follow you",
        link="/account",
    )
