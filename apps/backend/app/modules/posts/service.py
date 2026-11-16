"""Posts, reels, likes, comments, saves, hashtags and mentions. Visibility and blocks are enforced here."""

import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.errors import AppError, NotFound
from app.core.events import emit
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.accounts import repository as accounts_repo
from app.modules.accounts.models import User
from app.modules.media import service as media
from app.modules.media.service import AssetOut
from app.modules.posts.models import Comment, Like, Post, PostHashtag, Save
from app.modules.social import service as social

HASHTAG_RE = re.compile(r"(?<!\w)#([\wऀ-ॿ]{2,60})")
MENTION_RE = re.compile(r"(?<!\w)@([a-z0-9][a-z0-9_.]{1,28}[a-z0-9])", re.IGNORECASE)


class PostCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption: str | None = Field(default=None, max_length=2200)
    media_ids: list[uuid.UUID] = Field(default_factory=list, max_length=10)
    visibility: Literal["public", "followers"] = "public"
    kind: Literal["post", "reel"] = "post"


class Author(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str


class PostOut(BaseModel):
    id: uuid.UUID
    author: Author
    kind: str
    caption: str | None
    visibility: str
    media: list[AssetOut]
    like_count: int
    comment_count: int
    liked: bool
    saved: bool
    created_at: datetime


class PostPage(BaseModel):
    items: list[PostOut]
    next_cursor: str | None


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=1000)
    parent_id: uuid.UUID | None = None


class CommentOut(BaseModel):
    id: uuid.UUID
    author: Author
    parent_id: uuid.UUID | None
    body: str
    created_at: datetime


def hashtags(text: str | None) -> set[str]:
    return {t.lower() for t in HASHTAG_RE.findall(text or "")}


def mentions(text: str | None) -> set[str]:
    return {m.lower() for m in MENTION_RE.findall(text or "")}


async def hydrate(db: AsyncSession, posts: list[Post], viewer: User | None) -> list[PostOut]:
    if not posts:
        return []
    authors = await accounts_repo.get_users(db, list({p.author_id for p in posts}))
    asset_ids = [uuid.UUID(str(a)) for p in posts for a in p.media]
    assets = await media.public_views(db, asset_ids)
    ids = [p.id for p in posts]
    liked: set[uuid.UUID] = set()
    saved: set[uuid.UUID] = set()
    if viewer:
        liked = set((await db.scalars(select(Like.post_id).where(Like.user_id == viewer.id, Like.post_id.in_(ids)))).all())
        saved = set((await db.scalars(select(Save.post_id).where(Save.user_id == viewer.id, Save.post_id.in_(ids)))).all())
    out = []
    for p in posts:
        a = authors.get(p.author_id)
        if a is None:
            continue
        out.append(
            PostOut(
                id=p.id,
                author=Author(id=a.id, username=a.username, display_name=a.display_name),
                kind=p.kind,
                caption=p.caption,
                visibility=p.visibility,
                media=[assets[uuid.UUID(str(m))] for m in p.media if uuid.UUID(str(m)) in assets],
                like_count=p.like_count,
                comment_count=p.comment_count,
                liked=p.id in liked,
                saved=p.id in saved,
                created_at=p.created_at,
            )
        )
    return out


async def visible_post(db: AsyncSession, viewer: User | None, post_id: uuid.UUID) -> Post:
    p = await db.get(Post, post_id)
    if p is None or p.deleted_at is not None or p.status != "published":
        raise NotFound("post_not_found", "Post not found.")
    viewer_id = viewer.id if viewer else None
    if viewer_id and viewer_id != p.author_id and await social.blocked_between(db, viewer_id, p.author_id):
        raise NotFound("post_not_found", "Post not found.")
    if p.visibility == "followers" or await social.is_private(db, p.author_id):
        if not await social.can_view(db, viewer_id, p.author_id):
            raise NotFound("post_not_found", "Post not found.")
    return p


async def create(db: AsyncSession, user: User, data: PostCreate) -> PostOut:
    if not data.caption and not data.media_ids:
        raise AppError("empty_post", "Add a photo, video or caption.")
    await rate_limit.enforce("post_create", str(user.id), limit=30, window_s=3600)
    assets = await media.ready_assets(db, user.id, data.media_ids)
    if data.kind == "reel" and (len(assets) != 1 or assets[0].kind != "video"):
        raise AppError("reel_needs_video", "A reel is exactly one video.")
    post = Post(
        author_id=user.id, kind=data.kind, caption=data.caption, visibility=data.visibility, media=[str(a.id) for a in assets]
    )
    db.add(post)
    await db.flush()
    for tag in hashtags(data.caption):
        db.add(PostHashtag(tag=tag, post_id=post.id))
    mentioned = [
        u for u in [await accounts_repo.get_user_by_username(db, m) for m in mentions(data.caption)] if u and u.id != user.id
    ]
    emit(
        db,
        "posts.published",
        {
            "post_id": str(post.id),
            "author_id": str(user.id),
            "created_at": datetime.now(UTC).isoformat(),
            "mentioned_ids": [str(u.id) for u in mentioned],
            "author_name": user.display_name,
        },
    )
    await db.commit()
    return (await hydrate(db, [post], user))[0]


async def delete(db: AsyncSession, user: User, post_id: uuid.UUID) -> None:
    p = await db.get(Post, post_id)
    if p is None or p.author_id != user.id or p.deleted_at is not None:
        raise NotFound("post_not_found", "Post not found.")
    p.deleted_at = datetime.now(UTC)
    emit(db, "posts.deleted", {"post_id": str(p.id), "author_id": str(user.id)})
    await db.commit()


async def like(db: AsyncSession, user: User, post_id: uuid.UUID, on: bool) -> int:
    p = await visible_post(db, user, post_id)
    if on:
        inserted = await db.scalar(
            insert(Like).values(user_id=user.id, post_id=p.id).on_conflict_do_nothing().returning(Like.post_id)
        )
        if inserted:
            await db.execute(update(Post).where(Post.id == p.id).values(like_count=Post.like_count + 1))
            if p.author_id != user.id:
                emit(
                    db,
                    "posts.liked",
                    {
                        "post_id": str(p.id),
                        "author_id": str(p.author_id),
                        "liker_id": str(user.id),
                        "liker_name": user.display_name,
                    },
                )
    else:
        row = await db.get(Like, (user.id, p.id))
        if row:
            await db.delete(row)
            await db.execute(update(Post).where(Post.id == p.id).values(like_count=Post.like_count - 1))
    await db.commit()
    return int(await db.scalar(select(Post.like_count).where(Post.id == p.id)) or 0)


async def save(db: AsyncSession, user: User, post_id: uuid.UUID, on: bool, collection: str = "Saved") -> None:
    p = await visible_post(db, user, post_id)
    if on:
        await db.execute(insert(Save).values(user_id=user.id, post_id=p.id, collection=collection[:40]).on_conflict_do_nothing())
    else:
        row = await db.get(Save, (user.id, p.id))
        if row:
            await db.delete(row)
    await db.commit()


async def saved(db: AsyncSession, user: User) -> list[PostOut]:
    ids = (await db.scalars(select(Save.post_id).where(Save.user_id == user.id).order_by(Save.created_at.desc()).limit(50))).all()
    posts = (await db.scalars(select(Post).where(Post.id.in_(ids), Post.deleted_at.is_(None)))).all()
    hidden = await social.hidden_ids_for(db, user.id)
    return await hydrate(db, sorted([p for p in posts if p.author_id not in hidden], key=lambda p: ids.index(p.id)), user)


async def add_comment(db: AsyncSession, user: User, post_id: uuid.UUID, data: CommentIn) -> CommentOut:
    p = await visible_post(db, user, post_id)
    await rate_limit.enforce("comment_create", str(user.id), limit=60, window_s=3600)
    if data.parent_id:
        parent = await db.get(Comment, data.parent_id)
        if parent is None or parent.post_id != p.id:
            raise NotFound("comment_not_found", "Comment not found.")
        if parent.parent_id is not None:
            data.parent_id = parent.parent_id  # threads are one level deep; replies to replies attach to the thread
    c = Comment(post_id=p.id, author_id=user.id, parent_id=data.parent_id, body=data.body)
    db.add(c)
    await db.execute(update(Post).where(Post.id == p.id).values(comment_count=Post.comment_count + 1))
    await db.flush()
    mentioned = [
        u for u in [await accounts_repo.get_user_by_username(db, m) for m in mentions(data.body)] if u and u.id != user.id
    ]
    emit(
        db,
        "posts.commented",
        {
            "post_id": str(p.id),
            "comment_id": str(c.id),
            "author_id": str(p.author_id),
            "commenter_id": str(user.id),
            "commenter_name": user.display_name,
            "mentioned_ids": [str(u.id) for u in mentioned],
        },
    )
    await db.commit()
    return CommentOut(
        id=c.id,
        author=Author(id=user.id, username=user.username, display_name=user.display_name),
        parent_id=c.parent_id,
        body=c.body,
        created_at=c.created_at,
    )


async def comments(db: AsyncSession, viewer: User | None, post_id: uuid.UUID) -> list[CommentOut]:
    p = await visible_post(db, viewer, post_id)
    rows = (
        await db.scalars(
            select(Comment).where(Comment.post_id == p.id, Comment.status == "published").order_by(Comment.created_at).limit(200)
        )
    ).all()
    hidden = await social.hidden_ids_for(db, viewer.id) if viewer else set()
    authors = await accounts_repo.get_users(db, list({c.author_id for c in rows}))
    return [
        CommentOut(
            id=c.id,
            author=Author(id=a.id, username=a.username, display_name=a.display_name),
            parent_id=c.parent_id,
            body=c.body,
            created_at=c.created_at,
        )
        for c in rows
        if c.author_id not in hidden and (a := authors.get(c.author_id))
    ]


async def delete_comment(db: AsyncSession, user: User, comment_id: uuid.UUID) -> None:
    c = await db.get(Comment, comment_id)
    if c is None or c.status != "published":
        raise NotFound("comment_not_found", "Comment not found.")
    p = await db.get(Post, c.post_id)
    if user.id not in (c.author_id, p.author_id if p else None):  # own comment, or a comment on your post
        raise NotFound("comment_not_found", "Comment not found.")
    c.status = "removed"
    await db.execute(update(Post).where(Post.id == c.post_id).values(comment_count=Post.comment_count - 1))
    await db.commit()


def _cursor_filter(stmt, cursor: str | None):  # type: ignore[no-untyped-def]
    c = decode_cursor(cursor)
    if c:
        at, pid = datetime.fromisoformat(c["t"]), uuid.UUID(c["i"])
        stmt = stmt.where(or_(Post.created_at < at, and_(Post.created_at == at, Post.id < pid)))
    return stmt


def _page(items: list[PostOut], rows: list[Post], limit: int) -> PostPage:
    nxt = encode_cursor({"t": rows[-1].created_at.isoformat(), "i": str(rows[-1].id)}) if len(rows) == limit else None
    return PostPage(items=items, next_cursor=nxt)


async def by_author(db: AsyncSession, viewer: User | None, username: str, cursor: str | None, limit: int) -> PostPage:
    prof = await social.profile(db, viewer, username)  # 404 when blocked
    stmt = select(Post).where(Post.author_id == prof.id, Post.deleted_at.is_(None), Post.status == "published")
    if not prof.can_view_content:
        return PostPage(items=[], next_cursor=None)
    if prof.relationship not in ("self", "following"):
        stmt = stmt.where(Post.visibility == "public")
    rows = list(
        (await db.scalars(_cursor_filter(stmt, cursor).order_by(Post.created_at.desc(), Post.id.desc()).limit(limit))).all()
    )
    return _page(await hydrate(db, rows, viewer), rows, limit)


async def by_hashtag(db: AsyncSession, viewer: User | None, tag: str, cursor: str | None, limit: int) -> PostPage:
    ids = select(PostHashtag.post_id).where(PostHashtag.tag == tag.lower().lstrip("#"))
    stmt = select(Post).where(
        Post.id.in_(ids), Post.deleted_at.is_(None), Post.status == "published", Post.visibility == "public"
    )
    rows = list(
        (await db.scalars(_cursor_filter(stmt, cursor).order_by(Post.created_at.desc(), Post.id.desc()).limit(limit * 2))).all()
    )
    rows = await _public_filter(db, viewer, rows)
    return _page(await hydrate(db, rows[:limit], viewer), rows[:limit], limit)


async def reels(db: AsyncSession, viewer: User | None, cursor: str | None, limit: int) -> PostPage:
    stmt = select(Post).where(
        Post.kind == "reel", Post.deleted_at.is_(None), Post.status == "published", Post.visibility == "public"
    )
    rows = list(
        (await db.scalars(_cursor_filter(stmt, cursor).order_by(Post.created_at.desc(), Post.id.desc()).limit(limit * 2))).all()
    )
    rows = await _public_filter(db, viewer, rows)
    return _page(await hydrate(db, rows[:limit], viewer), rows[:limit], limit)


async def _public_filter(db: AsyncSession, viewer: User | None, rows: list[Post]) -> list[Post]:
    hidden = await social.hidden_ids_for(db, viewer.id) if viewer else set()
    out = []
    for p in rows:
        if p.author_id in hidden:
            continue
        if await social.is_private(db, p.author_id) and not await social.can_view(db, viewer.id if viewer else None, p.author_id):
            continue
        out.append(p)
    return out


async def get_posts(db: AsyncSession, ids: list[uuid.UUID]) -> list[Post]:
    if not ids:
        return []
    rows = {
        p.id: p
        for p in (
            await db.scalars(select(Post).where(Post.id.in_(ids), Post.deleted_at.is_(None), Post.status == "published"))
        ).all()
    }
    return [rows[i] for i in ids if i in rows]


async def recent_by_authors(db: AsyncSession, author_ids: list[uuid.UUID], before: datetime | None, limit: int) -> list[Post]:
    if not author_ids:
        return []
    stmt = select(Post).where(Post.author_id.in_(author_ids), Post.deleted_at.is_(None), Post.status == "published")
    if before:
        stmt = stmt.where(Post.created_at < before)
    return list((await db.scalars(stmt.order_by(Post.created_at.desc()).limit(limit))).all())


# --- Moderation interface (called from the moderation consumer, in its transaction) ---


async def remove_by_moderator(db: AsyncSession, post_id: uuid.UUID) -> None:
    p = await db.get(Post, post_id)
    if p is not None and p.status == "published":
        p.status = "removed"
        emit(db, "posts.deleted", {"post_id": str(p.id), "author_id": str(p.author_id)})


async def remove_comment_by_moderator(db: AsyncSession, comment_id: uuid.UUID) -> None:
    c = await db.get(Comment, comment_id)
    if c is not None and c.status == "published":
        c.status = "removed"
        await db.execute(update(Post).where(Post.id == c.post_id).values(comment_count=Post.comment_count - 1))
