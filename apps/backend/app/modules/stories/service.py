"""Stories: 24-hour expiry, viewer list (author only), highlights that keep selected stories."""

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, String, func, select
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.errors import NotFound
from app.core.ids import uuid7
from app.modules.accounts import repository as accounts_repo
from app.modules.accounts.models import User
from app.modules.media import service as media
from app.modules.media.service import AssetOut
from app.modules.social import service as social

STORY_TTL = timedelta(hours=24)


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = {"schema": "stories"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    audience: Mapped[str] = mapped_column(String(12), nullable=False, default="followers")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StoryView(Base):
    __tablename__ = "views"
    __table_args__ = {"schema": "stories"}  # noqa: RUF012
    story_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    viewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Highlight(Base):
    __tablename__ = "highlights"
    __table_args__ = {"schema": "stories"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class HighlightItem(Base):
    __tablename__ = "highlight_items"
    __table_args__ = {"schema": "stories"}  # noqa: RUF012
    highlight_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    story_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)


class StoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: uuid.UUID


class StoryOut(BaseModel):
    id: uuid.UUID
    media: AssetOut
    created_at: datetime
    expires_at: datetime
    seen: bool


class StoryGroup(BaseModel):
    author_id: uuid.UUID
    username: str
    display_name: str
    stories: list[StoryOut]
    all_seen: bool


class HighlightIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=40)
    story_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)


class HighlightOut(BaseModel):
    id: uuid.UUID
    title: str
    stories: list[StoryOut]


async def create(db: AsyncSession, user: User, data: StoryCreate) -> StoryOut:
    asset = (await media.ready_assets(db, user.id, [data.asset_id]))[0]
    now = datetime.now(UTC)
    s = Story(author_id=user.id, asset_id=asset.id, created_at=now, expires_at=now + STORY_TTL)
    db.add(s)
    await db.commit()
    return StoryOut(id=s.id, media=asset, created_at=s.created_at, expires_at=s.expires_at, seen=True)


async def _outs(db: AsyncSession, rows: list[Story], viewer_id: uuid.UUID) -> list[StoryOut]:
    assets = await media.public_views(db, [r.asset_id for r in rows])
    seen = (
        set(
            (
                await db.scalars(
                    select(StoryView.story_id).where(
                        StoryView.viewer_id == viewer_id, StoryView.story_id.in_([r.id for r in rows])
                    )
                )
            ).all()
        )
        if rows
        else set()
    )
    return [
        StoryOut(
            id=r.id,
            media=assets[r.asset_id],
            created_at=r.created_at,
            expires_at=r.expires_at,
            seen=r.id in seen or r.author_id == viewer_id,
        )
        for r in rows
        if r.asset_id in assets
    ]


async def tray(db: AsyncSession, viewer: User) -> list[StoryGroup]:
    authors = [viewer.id, *await social.following_ids(db, viewer.id)]
    hidden = await social.hidden_ids_for(db, viewer.id)
    now = datetime.now(UTC)
    rows = (
        await db.scalars(
            select(Story)
            .where(Story.author_id.in_([a for a in authors if a not in hidden]), Story.expires_at > now)
            .order_by(Story.created_at)
        )
    ).all()
    users = await accounts_repo.get_users(db, list({r.author_id for r in rows}))
    groups: dict[uuid.UUID, list[Story]] = {}
    for r in rows:
        groups.setdefault(r.author_id, []).append(r)
    out = []
    for author_id, items in groups.items():
        u = users.get(author_id)
        if not u:
            continue
        outs = await _outs(db, items, viewer.id)
        out.append(
            StoryGroup(
                author_id=author_id,
                username=u.username,
                display_name=u.display_name,
                stories=outs,
                all_seen=all(s.seen for s in outs),
            )
        )
    out.sort(key=lambda g: (g.author_id != viewer.id, g.all_seen))
    return out


async def view(db: AsyncSession, viewer: User, story_id: uuid.UUID) -> None:
    s = await db.get(Story, story_id)
    if s is None or s.expires_at <= datetime.now(UTC) or not await social.can_view(db, viewer.id, s.author_id):
        raise NotFound("story_not_found", "Story not found.")
    if s.author_id != viewer.id:
        await db.execute(insert(StoryView).values(story_id=s.id, viewer_id=viewer.id).on_conflict_do_nothing())
        await db.commit()


async def viewers(db: AsyncSession, author: User, story_id: uuid.UUID) -> list[dict[str, str]]:
    s = await db.get(Story, story_id)
    if s is None or s.author_id != author.id:
        raise NotFound("story_not_found", "Story not found.")
    ids = (await db.scalars(select(StoryView.viewer_id).where(StoryView.story_id == s.id).order_by(StoryView.viewed_at))).all()
    users = await accounts_repo.get_users(db, list(ids))
    return [{"username": users[i].username, "display_name": users[i].display_name} for i in ids if i in users]


async def create_highlight(db: AsyncSession, user: User, data: HighlightIn) -> HighlightOut:
    rows = (await db.scalars(select(Story).where(Story.id.in_(data.story_ids), Story.author_id == user.id))).all()
    if len(rows) != len(set(data.story_ids)):
        raise NotFound("story_not_found", "Story not found.")
    h = Highlight(owner_id=user.id, title=data.title)
    db.add(h)
    await db.flush()
    db.add_all(HighlightItem(highlight_id=h.id, story_id=s.id) for s in rows)
    await db.commit()
    return HighlightOut(id=h.id, title=h.title, stories=await _outs(db, list(rows), user.id))


async def highlights(db: AsyncSession, viewer: User | None, username: str) -> list[HighlightOut]:
    prof = await social.profile(db, viewer, username)
    if not prof.can_view_content:
        return []
    hs = (await db.scalars(select(Highlight).where(Highlight.owner_id == prof.id).order_by(Highlight.created_at))).all()
    out = []
    for h in hs:
        ids = (await db.scalars(select(HighlightItem.story_id).where(HighlightItem.highlight_id == h.id))).all()
        rows = (await db.scalars(select(Story).where(Story.id.in_(ids)).order_by(Story.created_at))).all()
        out.append(HighlightOut(id=h.id, title=h.title, stories=await _outs(db, list(rows), viewer.id if viewer else prof.id)))
    return out
