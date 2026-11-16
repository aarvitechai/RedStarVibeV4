"""Accounts: signup, login, refresh rotation with reuse detection, logout, sessions."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.errors import AppError, Conflict, Unauthorized
from app.core.events import emit
from app.core.ids import uuid7
from app.core.permissions import ROLES
from app.core.security import (
    REFRESH_TOKEN_TTL,
    create_access_token,
    hash_password,
    hash_token,
    needs_rehash,
    new_refresh_token,
    verify_password,
)
from app.modules.accounts import repository as repo
from app.modules.accounts.models import LoginEvent, Session, User
from app.modules.accounts.schemas import LoginRequest, SignupRequest
from app.modules.audit import service as audit


@dataclass(frozen=True)
class ClientInfo:
    ip: str
    user_agent: str | None


@dataclass(frozen=True)
class IssuedTokens:
    user: User
    access_token: str
    refresh_token: str
    family_id: uuid.UUID


async def _issue(db: AsyncSession, user: User, client: ClientInfo, family_id: uuid.UUID | None = None) -> IssuedTokens:
    family = family_id or uuid7()
    refresh = new_refresh_token()
    await repo.add_session(
        db,
        Session(
            user_id=user.id,
            family_id=family,
            token_hash=hash_token(refresh),
            expires_at=datetime.now(UTC) + REFRESH_TOKEN_TTL,
            user_agent=(client.user_agent or "")[:300] or None,
            ip=client.ip,
        ),
    )
    return IssuedTokens(user, create_access_token(user.id, family, user.role), refresh, family)


async def signup(db: AsyncSession, data: SignupRequest, client: ClientInfo) -> IssuedTokens:
    await rate_limit.enforce("signup", client.ip, limit=10, window_s=3600)
    taken_username, taken_email = await repo.exists_username_or_email(db, data.username, str(data.email))
    if taken_username:
        raise Conflict("username_taken", "This username is already taken.")
    if taken_email:
        # Same wording an attacker would see for a fresh address is not possible here without email verification;
        # we accept this enumeration until email verification ships (Phase 1 backlog).
        raise Conflict("email_taken", "An account with this email already exists.")
    user = User(
        username=data.username,
        email=str(data.email).lower(),
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        role="user",
        status="active",
        is_adult_confirmed=True,
    )
    try:
        await repo.add_user(db, user)
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict("account_exists", "This username or email is already taken.") from exc
    tokens = await _issue(db, user, client)
    emit(db, "accounts.user_signed_up", {"user_id": str(user.id), "username": user.username})
    await db.commit()
    return tokens


async def login(db: AsyncSession, data: LoginRequest, client: ClientInfo) -> IssuedTokens:
    email = str(data.email).lower()
    await rate_limit.enforce("login_ip", client.ip, limit=20, window_s=60)
    await rate_limit.enforce("login_account", email, limit=5, window_s=60)
    user = await repo.get_user_by_email(db, email)
    ok = verify_password(user.password_hash if user else None, data.password)
    if not user or not ok or user.status != "active":
        reason = "bad_credentials" if not user or not ok else f"status_{user.status}"
        await repo.add_login_event(
            db,
            LoginEvent(
                user_id=user.id if user else None,
                success=False,
                reason=reason,
                ip=client.ip,
                user_agent=(client.user_agent or "")[:300] or None,
            ),
        )
        await db.commit()
        raise Unauthorized("invalid_credentials", "Email or password is incorrect.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
    tokens = await _issue(db, user, client)
    await repo.add_login_event(
        db, LoginEvent(user_id=user.id, success=True, ip=client.ip, user_agent=(client.user_agent or "")[:300] or None)
    )
    await db.commit()
    await rate_limit.reset("login_account", email)
    return tokens


async def refresh(db: AsyncSession, refresh_token: str | None, client: ClientInfo) -> IssuedTokens:
    if not refresh_token:
        raise Unauthorized("refresh_missing", "Please sign in again.")
    current = await repo.get_session_by_hash(db, hash_token(refresh_token), lock=True)
    if current is None:
        raise Unauthorized("refresh_invalid", "Please sign in again.")
    if current.rotated_at is not None or current.revoked_at is not None:
        # An already-used token came back: assume theft and revoke the whole login (Blueprint 12.1).
        await repo.revoke_family(db, current.user_id, current.family_id)
        await audit.record(
            db,
            actor_id=current.user_id,
            action="session.refresh_reuse_detected",
            target_type="session",
            target_id=str(current.family_id),
            ip=client.ip,
        )
        await db.commit()
        raise Unauthorized("refresh_reused", "Please sign in again.")
    if current.expires_at <= datetime.now(UTC):
        raise Unauthorized("refresh_expired", "Please sign in again.")
    user = await repo.get_user(db, current.user_id)
    if user is None or user.status != "active":
        raise Unauthorized("account_inactive", "Please sign in again.")
    current.rotated_at = datetime.now(UTC)
    tokens = await _issue(db, user, client, family_id=current.family_id)
    await db.commit()
    return tokens


async def logout(db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
    await repo.revoke_family(db, user_id, family_id)
    await db.commit()


async def logout_other_devices(db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID) -> None:
    await repo.revoke_all_except(db, user_id, family_id)
    await db.commit()


async def change_role(db: AsyncSession, actor: User, target_id: uuid.UUID, role: str, ip: str) -> User:
    if role not in ROLES:
        raise AppError("invalid_role", "Unknown role.")
    if role == "superadmin":
        raise AppError("superadmin_via_script", "Super admins are created only with scripts/make_superadmin.py.")
    target = await repo.get_user(db, target_id)
    if target is None:
        from app.core.errors import NotFound

        raise NotFound()
    old = target.role
    await repo.set_role(db, target_id, role)
    await audit.record(
        db,
        actor_id=actor.id,
        action="user.role_changed",
        target_type="user",
        target_id=str(target_id),
        ip=ip,
        details={"from": old, "to": role},
    )
    await db.commit()
    await db.refresh(target)
    return target
