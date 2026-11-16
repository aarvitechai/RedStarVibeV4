"""Profiles, follows (with requests for private accounts), blocks and mutes.

Block rule (Blueprint P4 exit): two users who block each other in either direction cannot see each other's
profile, posts, stories or comments, cannot follow, and cannot message. Other modules ask `blocked_between`
and `hidden_ids_for`, never these tables.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, delete, func, or_, select, union, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFound
from app.core.events import emit
from app.modules.accounts import repository as accounts_repo
from app.modules.accounts.models import User
from app.modules.media import service as media
from app.modules.social.models import Block, Follow, Mute, Profile

CELEBRITY_FOLLOWERS = 5000  # above this, posts are merged at read time instead of fanned out (Blueprint 9.2)


class ProfileOut(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    bio: str | None
    website: str | None
    avatar: dict[str, str]
    is_private: bool
    followers: int
    following: int
    relationship: str  # self | following | requested | none
    can_view_content: bool


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bio: str | None = Field(default=None, max_length=300)
    website: str | None = Field(default=None, max_length=200, pattern=r"^https?://")
    is_private: bool | None = None
    avatar_asset_id: uuid.UUID | None = None


class UserCard(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    created_at: datetime


async def blocked_between(db: AsyncSession, a: uuid.UUID, b: uuid.UUID) -> bool:
    return (
        await db.scalar(
            select(Block.blocker_id)
            .where(or_(and_(Block.blocker_id == a, Block.blocked_id == b), and_(Block.blocker_id == b, Block.blocked_id == a)))
            .limit(1)
        )
        is not None
    )


async def hidden_ids_for(db: AsyncSession, viewer: uuid.UUID) -> set[uuid.UUID]:
    """Users whose content the viewer must not see: blocked either way, plus muted by the viewer."""
    rows = await db.execute(
        union(
            select(Block.blocked_id).where(Block.blocker_id == viewer),
            select(Block.blocker_id).where(Block.blocked_id == viewer),
            select(Mute.muted_id).where(Mute.muter_id == viewer),
        )
    )
    return {r[0] for r in rows}


async def blocked_ids_for(db: AsyncSession, viewer: uuid.UUID) -> set[uuid.UUID]:
    rows = await db.execute(
        union(
            select(Block.blocked_id).where(Block.blocker_id == viewer),
            select(Block.blocker_id).where(Block.blocked_id == viewer),
        )
    )
    return {r[0] for r in rows}


async def is_private(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return bool(await db.scalar(select(Profile.is_private).where(Profile.user_id == user_id)))


async def follows(db: AsyncSession, follower: uuid.UUID, followee: uuid.UUID) -> bool:
    return (
        await db.scalar(select(Follow.status).where(Follow.follower_id == follower, Follow.followee_id == followee)) == "active"
    )


async def can_view(db: AsyncSession, viewer: uuid.UUID | None, author: uuid.UUID) -> bool:
    """May `viewer` see `author`'s non-public-only content (followers-visibility posts, stories)?"""
    if viewer == author:
        return True
    if viewer is None:
        return not await is_private(db, author)
    if await blocked_between(db, viewer, author):
        return False
    return not await is_private(db, author) or await follows(db, viewer, author)


async def follower_ids(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (await db.scalars(select(Follow.follower_id).where(Follow.followee_id == user_id, Follow.status == "active"))).all()
    )


async def following_ids(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (await db.scalars(select(Follow.followee_id).where(Follow.follower_id == user_id, Follow.status == "active"))).all()
    )


async def follower_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    return int(await db.scalar(select(func.count()).where(Follow.followee_id == user_id, Follow.status == "active")) or 0)


async def profile(db: AsyncSession, viewer: User | None, username: str) -> ProfileOut:
    user = await accounts_repo.get_user_by_username(db, username)
    if user is None or user.status != "active" or (viewer and await blocked_between(db, viewer.id, user.id)):
        raise NotFound("profile_not_found", "Profile not found.")
    p = await db.get(Profile, user.id)
    rel = "none"
    if viewer and viewer.id == user.id:
        rel = "self"
    elif viewer:
        st = await db.scalar(select(Follow.status).where(Follow.follower_id == viewer.id, Follow.followee_id == user.id))
        rel = {"active": "following", "pending": "requested"}.get(st or "", "none")
    following = int(await db.scalar(select(func.count()).where(Follow.follower_id == user.id, Follow.status == "active")) or 0)
    avatar = {}
    if p and p.avatar_asset_id:
        views = await media.public_views(db, [p.avatar_asset_id])
        avatar = views[p.avatar_asset_id].urls if p.avatar_asset_id in views else {}
    return ProfileOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        bio=p.bio if p else None,
        website=p.website if p else None,
        avatar=avatar,
        is_private=bool(p and p.is_private),
        followers=await follower_count(db, user.id),
        following=following,
        relationship=rel,
        can_view_content=await can_view(db, viewer.id if viewer else None, user.id),
    )


async def update_profile(db: AsyncSession, user: User, data: ProfileUpdate) -> ProfileOut:
    changes = data.model_dump(exclude_unset=True)
    if changes.get("avatar_asset_id"):
        await media.ready_assets(db, user.id, [changes["avatar_asset_id"]])
    await db.execute(
        insert(Profile)
        .values(user_id=user.id, **changes)
        .on_conflict_do_update(index_elements=["user_id"], set_={**changes, "updated_at": func.now()})
        if changes
        else insert(Profile).values(user_id=user.id).on_conflict_do_nothing()
    )
    if changes.get("is_private") is False:
        # Going public approves all pending requests.
        await db.execute(update(Follow).where(Follow.followee_id == user.id, Follow.status == "pending").values(status="active"))
    await db.commit()
    return await profile(db, user, user.username)


async def follow(db: AsyncSession, user: User, username: str) -> str:
    target = await accounts_repo.get_user_by_username(db, username)
    if target is None or target.id == user.id or await blocked_between(db, user.id, target.id):
        raise NotFound("profile_not_found", "Profile not found.")
    status = "pending" if await is_private(db, target.id) else "active"
    inserted = await db.scalar(
        insert(Follow)
        .values(follower_id=user.id, followee_id=target.id, status=status)
        .on_conflict_do_nothing()
        .returning(Follow.status)
    )
    if inserted:
        emit(
            db,
            "social.followed" if status == "active" else "social.follow_requested",
            {"follower_id": str(user.id), "followee_id": str(target.id), "follower_name": user.display_name},
        )
    await db.commit()
    return str(
        inserted or await db.scalar(select(Follow.status).where(Follow.follower_id == user.id, Follow.followee_id == target.id))
    )


async def unfollow(db: AsyncSession, user: User, username: str) -> None:
    target = await accounts_repo.get_user_by_username(db, username)
    if target is not None:
        await db.execute(delete(Follow).where(Follow.follower_id == user.id, Follow.followee_id == target.id))
        emit(db, "social.unfollowed", {"follower_id": str(user.id), "followee_id": str(target.id)})
        await db.commit()


async def pending_requests(db: AsyncSession, user: User) -> list[UserCard]:
    ids = (await db.scalars(select(Follow.follower_id).where(Follow.followee_id == user.id, Follow.status == "pending"))).all()
    return [
        UserCard(id=u.id, username=u.username, display_name=u.display_name, created_at=u.created_at)
        for u in [await accounts_repo.get_user(db, i) for i in ids]
        if u
    ]


async def answer_request(db: AsyncSession, user: User, follower_username: str, approve: bool) -> None:
    follower = await accounts_repo.get_user_by_username(db, follower_username)
    if follower is None:
        raise NotFound("request_not_found", "Request not found.")
    row = await db.get(Follow, (follower.id, user.id))
    if row is None or row.status != "pending":
        raise NotFound("request_not_found", "Request not found.")
    if approve:
        row.status = "active"
        emit(
            db,
            "social.followed",
            {"follower_id": str(follower.id), "followee_id": str(user.id), "follower_name": follower.display_name},
        )
    else:
        await db.delete(row)
    await db.commit()


async def block(db: AsyncSession, user: User, username: str) -> None:
    target = await accounts_repo.get_user_by_username(db, username)
    if target is None or target.id == user.id:
        raise AppError("cannot_block", "You cannot block this account.")
    await db.execute(insert(Block).values(blocker_id=user.id, blocked_id=target.id).on_conflict_do_nothing())
    # Blocking removes follows in both directions.
    await db.execute(
        delete(Follow).where(
            or_(
                and_(Follow.follower_id == user.id, Follow.followee_id == target.id),
                and_(Follow.follower_id == target.id, Follow.followee_id == user.id),
            )
        )
    )
    emit(db, "social.blocked", {"blocker_id": str(user.id), "blocked_id": str(target.id)})
    await db.commit()


async def unblock(db: AsyncSession, user: User, username: str) -> None:
    target = await accounts_repo.get_user_by_username(db, username)
    if target is not None:
        await db.execute(delete(Block).where(Block.blocker_id == user.id, Block.blocked_id == target.id))
        await db.commit()


async def mute(db: AsyncSession, user: User, username: str, on: bool) -> None:
    target = await accounts_repo.get_user_by_username(db, username)
    if target is None or target.id == user.id:
        raise NotFound("profile_not_found", "Profile not found.")
    if on:
        await db.execute(insert(Mute).values(muter_id=user.id, muted_id=target.id).on_conflict_do_nothing())
    else:
        await db.execute(delete(Mute).where(Mute.muter_id == user.id, Mute.muted_id == target.id))
    await db.commit()


async def search_users(db: AsyncSession, viewer: User | None, q: str, limit: int = 20) -> list[UserCard]:
    rows = await accounts_repo.search_users(db, q, limit + 20)
    hidden = await blocked_ids_for(db, viewer.id) if viewer else set()
    return [
        UserCard(id=u.id, username=u.username, display_name=u.display_name, created_at=u.created_at)
        for u in rows
        if u.id not in hidden
    ][:limit]
