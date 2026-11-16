import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accounts.models import LoginEvent, Session, User


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    return await db.scalar(select(User).where(User.username == username, User.deleted_at.is_(None)))


async def exists_username_or_email(db: AsyncSession, username: str, email: str) -> tuple[bool, bool]:
    rows = (await db.execute(select(User.username, User.email).where((User.username == username) | (User.email == email)))).all()
    return (any(r.username.lower() == username.lower() for r in rows), any(r.email.lower() == email.lower() for r in rows))


async def add_user(db: AsyncSession, user: User) -> User:
    db.add(user)
    await db.flush()
    return user


async def set_role(db: AsyncSession, user_id: uuid.UUID, role: str) -> None:
    await db.execute(update(User).where(User.id == user_id).values(role=role, updated_at=func.now()))


async def add_session(db: AsyncSession, session: Session) -> Session:
    db.add(session)
    await db.flush()
    return session


async def get_session_by_hash(db: AsyncSession, token_hash: str, *, lock: bool = False) -> Session | None:
    stmt = select(Session).where(Session.token_hash == token_hash)
    if lock:
        stmt = stmt.with_for_update()
    return await db.scalar(stmt)


async def family_is_active(db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID) -> bool:
    """A login is active while its family has an unrevoked, unexpired, unrotated token."""
    now = datetime.now(UTC)
    row = await db.scalar(
        select(Session.id)
        .where(
            Session.user_id == user_id,
            Session.family_id == family_id,
            Session.revoked_at.is_(None),
            Session.rotated_at.is_(None),
            Session.expires_at > now,
        )
        .limit(1)
    )
    return row is not None


async def revoke_family(db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
    await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.family_id == family_id, Session.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )


async def revoke_all_except(db: AsyncSession, user_id: uuid.UUID, keep_family: uuid.UUID) -> None:
    await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.family_id != keep_family, Session.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )


async def list_active_families(db: AsyncSession, user_id: uuid.UUID) -> list[Session]:
    now = datetime.now(UTC)
    rows = await db.scalars(
        select(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None), Session.rotated_at.is_(None), Session.expires_at > now)
        .order_by(Session.created_at.desc())
    )
    return list(rows)


async def add_login_event(db: AsyncSession, event: LoginEvent) -> None:
    db.add(event)


async def search_users(db: AsyncSession, q: str, limit: int) -> list[User]:
    """Prefix/trigram search on username and display name (pg_trgm)."""
    pattern = f"%{q.strip().lower().replace('%', '').replace('_', '')}%"
    rows = await db.scalars(
        select(User)
        .where(
            User.status == "active",
            User.deleted_at.is_(None),
            (func.lower(User.username).like(pattern)) | (func.lower(User.display_name).like(pattern)),
        )
        .order_by(func.length(User.username))
        .limit(limit)
    )
    return list(rows)


async def get_users(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
    if not ids:
        return {}
    return {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()}
