"""Direct and group messages. Persist first, then deliver over WebSocket. Never indexed for AI/RAG (Blueprint 11.3)."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, DateTime, String, UniqueConstraint, func, select, update
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core import rate_limit
from app.core.database import Base
from app.core.errors import AppError, Forbidden, NotFound
from app.core.events import emit
from app.core.ids import uuid7
from app.modules.accounts import repository as accounts_repo
from app.modules.accounts.models import User
from app.modules.media import service as media
from app.modules.media.service import AssetOut
from app.modules.social import service as social
from app.realtime import hub

MAX_GROUP = 64


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = {"schema": "chat"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # direct | group
    title: Mapped[str | None] = mapped_column(String(80))
    direct_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    last_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Member(Base):
    __tablename__ = "members"
    __table_args__ = {"schema": "chat"}  # noqa: RUF012
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(String(8), nullable=False, default="member")
    last_read_seq: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("conversation_id", "seq", name="ux_messages_seq"), {"schema": "chat"})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    body: Mapped[str | None] = mapped_column(String(4000))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    client_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str | None = Field(default=None, max_length=4000)
    asset_id: uuid.UUID | None = None
    client_id: str | None = Field(
        default=None, max_length=64, description="Client-generated id; retries with the same id are deduplicated"
    )


class GroupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=80)
    usernames: list[str] = Field(min_length=1, max_length=MAX_GROUP - 1)


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    seq: int
    sender_id: uuid.UUID
    body: str | None
    attachment: AssetOut | None
    client_id: str | None
    created_at: datetime


class MemberOut(BaseModel):
    user_id: uuid.UUID
    username: str
    display_name: str
    role: str


class ConversationOut(BaseModel):
    id: uuid.UUID
    kind: Literal["direct", "group"]
    title: str
    members: list[MemberOut]
    last_seq: int
    unread: int
    last_message_at: datetime | None


async def _member(db: AsyncSession, conv_id: uuid.UUID, user_id: uuid.UUID) -> Member:
    m = await db.get(Member, (conv_id, user_id))
    if m is None or m.left_at is not None:
        raise NotFound("conversation_not_found", "Conversation not found.")
    return m


async def _active_member_ids(db: AsyncSession, conv_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (await db.scalars(select(Member.user_id).where(Member.conversation_id == conv_id, Member.left_at.is_(None)))).all()
    )


async def _out(db: AsyncSession, c: Conversation, viewer: User) -> ConversationOut:
    rows = (await db.scalars(select(Member).where(Member.conversation_id == c.id, Member.left_at.is_(None)))).all()
    users = await accounts_repo.get_users(db, [m.user_id for m in rows])
    members = [
        MemberOut(user_id=m.user_id, username=users[m.user_id].username, display_name=users[m.user_id].display_name, role=m.role)
        for m in rows
        if m.user_id in users
    ]
    mine = next((m for m in rows if m.user_id == viewer.id), None)
    title = c.title or next((m.display_name for m in members if m.user_id != viewer.id), "Chat")
    return ConversationOut(
        id=c.id,
        kind=c.kind,
        title=title,
        members=members,
        last_seq=c.last_seq,
        unread=max(0, c.last_seq - (mine.last_read_seq if mine else 0)),
        last_message_at=c.last_message_at,
    )


async def direct(db: AsyncSession, user: User, username: str) -> ConversationOut:
    other = await accounts_repo.get_user_by_username(db, username)
    if other is None or other.id == user.id or await social.blocked_between(db, user.id, other.id):
        raise NotFound("profile_not_found", "Profile not found.")
    key = ":".join(sorted([str(user.id), str(other.id)]))
    c = await db.scalar(select(Conversation).where(Conversation.direct_key == key))
    if c is None:
        cid = uuid7()
        inserted = await db.scalar(
            insert(Conversation)
            .values(id=cid, kind="direct", direct_key=key, created_by=user.id, last_seq=0)
            .on_conflict_do_nothing()
            .returning(Conversation.id)
        )
        if inserted:
            await db.execute(
                insert(Member).values(
                    [
                        {"conversation_id": cid, "user_id": user.id, "role": "member", "last_read_seq": 0},
                        {"conversation_id": cid, "user_id": other.id, "role": "member", "last_read_seq": 0},
                    ]
                )
            )
        await db.commit()
        c = await db.scalar(select(Conversation).where(Conversation.direct_key == key))
    assert c is not None
    return await _out(db, c, user)


async def create_group(db: AsyncSession, user: User, data: GroupIn) -> ConversationOut:
    others = []
    for name in dict.fromkeys(u.lower() for u in data.usernames):
        u = await accounts_repo.get_user_by_username(db, name)
        if u is None or u.id == user.id or await social.blocked_between(db, user.id, u.id):
            raise NotFound("profile_not_found", f"@{name} was not found.")
        others.append(u)
    c = Conversation(kind="group", title=data.title, created_by=user.id)
    db.add(c)
    await db.flush()
    db.add(Member(conversation_id=c.id, user_id=user.id, role="owner"))
    db.add_all(Member(conversation_id=c.id, user_id=u.id, role="member") for u in others)
    await db.commit()
    return await _out(db, c, user)


async def conversations(db: AsyncSession, user: User) -> list[ConversationOut]:
    ids = select(Member.conversation_id).where(Member.user_id == user.id, Member.left_at.is_(None))
    rows = (
        await db.scalars(
            select(Conversation)
            .where(Conversation.id.in_(ids))
            .order_by(Conversation.last_message_at.desc().nulls_last())
            .limit(100)
        )
    ).all()
    return [await _out(db, c, user) for c in rows]


def _msg_out(m: Message, attachment: AssetOut | None) -> MessageOut:
    return MessageOut(
        id=m.id,
        conversation_id=m.conversation_id,
        seq=m.seq,
        sender_id=m.sender_id,
        body=m.body,
        attachment=attachment,
        client_id=m.client_id,
        created_at=m.created_at,
    )


async def send(db: AsyncSession, user: User, conv_id: uuid.UUID, data: MessageIn) -> MessageOut:
    if not (data.body and data.body.strip()) and not data.asset_id:
        raise AppError("empty_message", "Type a message or attach a file.")
    await _member(db, conv_id, user.id)
    await rate_limit.enforce("dm_send", str(user.id), limit=60, window_s=60)
    if data.client_id:
        dup = await db.scalar(
            select(Message).where(
                Message.conversation_id == conv_id, Message.sender_id == user.id, Message.client_id == data.client_id
            )
        )
        if dup:
            return _msg_out(dup, None)
    conv = await db.get(Conversation, conv_id)
    assert conv is not None
    if conv.kind == "direct":
        others = [m for m in await _active_member_ids(db, conv_id) if m != user.id]
        if others and await social.blocked_between(db, user.id, others[0]):
            raise Forbidden("blocked", "You cannot message this account.")
    attachment = (await media.ready_assets(db, user.id, [data.asset_id]))[0] if data.asset_id else None
    # Row lock on the conversation serialises seq allocation, so seq is gap-free and ordered.
    seq = await db.scalar(
        update(Conversation)
        .where(Conversation.id == conv_id)
        .values(last_seq=Conversation.last_seq + 1, last_message_at=func.now())
        .returning(Conversation.last_seq)
    )
    msg = Message(
        conversation_id=conv_id,
        seq=int(seq or 0),
        sender_id=user.id,
        body=data.body,
        asset_id=attachment.id if attachment else None,
        client_id=data.client_id,
    )
    db.add(msg)
    await db.execute(
        update(Member).where(Member.conversation_id == conv_id, Member.user_id == user.id).values(last_read_seq=msg.seq)
    )
    emit(
        db,
        "chat.message_sent",
        {"conversation_id": str(conv_id), "seq": msg.seq, "sender_id": str(user.id), "sender_name": user.display_name},
    )  # for offline push; body is not copied
    await db.commit()
    out = _msg_out(msg, attachment)
    await hub.publish(await _active_member_ids(db, conv_id), {"type": "message.new", "message": out.model_dump(mode="json")})
    return out


async def messages(
    db: AsyncSession, user: User, conv_id: uuid.UUID, after_seq: int | None, before_seq: int | None, limit: int
) -> list[MessageOut]:
    await _member(db, conv_id, user.id)
    stmt = select(Message).where(Message.conversation_id == conv_id)
    if after_seq is not None:
        rows = (await db.scalars(stmt.where(Message.seq > after_seq).order_by(Message.seq).limit(limit))).all()
    else:
        if before_seq is not None:
            stmt = stmt.where(Message.seq < before_seq)
        rows = list(reversed((await db.scalars(stmt.order_by(Message.seq.desc()).limit(limit))).all()))
    assets = await media.public_views(db, [m.asset_id for m in rows if m.asset_id])
    return [_msg_out(m, assets.get(m.asset_id) if m.asset_id else None) for m in rows]


async def mark_read(db: AsyncSession, user: User, conv_id: uuid.UUID, seq: int) -> None:
    m = await _member(db, conv_id, user.id)
    conv = await db.get(Conversation, conv_id)
    new = min(seq, conv.last_seq if conv else seq)
    if new > m.last_read_seq:
        m.last_read_seq = new
        await db.commit()
        await hub.publish(
            await _active_member_ids(db, conv_id),
            {"type": "receipt.read", "conversation_id": str(conv_id), "user_id": str(user.id), "seq": new},
        )


async def typing(db: AsyncSession, user: User, conv_id: uuid.UUID) -> None:
    await _member(db, conv_id, user.id)
    others = [u for u in await _active_member_ids(db, conv_id) if u != user.id]
    await hub.publish(others, {"type": "typing", "conversation_id": str(conv_id), "user_id": str(user.id)})


async def leave(db: AsyncSession, user: User, conv_id: uuid.UUID) -> None:
    m = await _member(db, conv_id, user.id)
    conv = await db.get(Conversation, conv_id)
    if conv and conv.kind == "direct":
        raise AppError("cannot_leave_direct", "Block or mute the person instead.")
    m.left_at = datetime.now(UTC)
    await db.commit()


async def remove_member(db: AsyncSession, owner: User, conv_id: uuid.UUID, username: str) -> None:
    me = await _member(db, conv_id, owner.id)
    if me.role != "owner":
        raise Forbidden("not_group_owner", "Only the group owner can remove members.")
    target = await accounts_repo.get_user_by_username(db, username)
    if target is None or target.id == owner.id:
        raise NotFound("member_not_found", "Member not found.")
    m = await _member(db, conv_id, target.id)
    m.left_at = datetime.now(UTC)
    await db.commit()


async def member_conversation_ids(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (await db.scalars(select(Member.conversation_id).where(Member.user_id == user_id, Member.left_at.is_(None)))).all()
    )


async def call_members(db: AsyncSession, user: User, conv_id: uuid.UUID) -> list[uuid.UUID]:
    """Active members of a conversation; raises 404 unless `user` is one of them."""
    await _member(db, conv_id, user.id)
    return await _active_member_ids(db, conv_id)
