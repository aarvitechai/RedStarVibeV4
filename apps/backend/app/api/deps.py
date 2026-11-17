"""Shared request dependencies: DB session, current user, permission checks."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import access_cookie_name
from app.core.database import get_session
from app.core.errors import Forbidden, Unauthorized
from app.core.net import client_ip
from app.core.permissions import PRIVILEGED_ROLES, has_permission
from app.core.security import AccessClaims, TokenExpired, TokenInvalid, decode_access_token
from app.modules.accounts import repository as accounts_repo
from app.modules.accounts.models import User
from app.modules.accounts.service import ClientInfo

DB = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class Principal:
    user: User
    claims: AccessClaims


async def _principal(request: Request, db: DB) -> Principal:
    token = request.cookies.get(access_cookie_name())
    if not token:
        raise Unauthorized("not_signed_in", "Please sign in.")
    try:
        claims = decode_access_token(token)
    except TokenExpired as exc:
        raise Unauthorized("token_expired", "Your session expired. Refreshing…") from exc
    except TokenInvalid as exc:
        raise Unauthorized("token_invalid", "Please sign in again.") from exc
    # Checked on every request so logout and "log out other devices" take effect immediately.
    if not await accounts_repo.family_is_active(db, claims.user_id, claims.session_family):
        raise Unauthorized("session_revoked", "Please sign in again.")
    user = await accounts_repo.get_user(db, claims.user_id)
    if user is None or user.status != "active":
        raise Unauthorized("account_inactive", "Please sign in again.")
    return Principal(user, claims)


CurrentPrincipal = Annotated[Principal, Depends(_principal)]


async def _current_user(p: CurrentPrincipal) -> User:
    return p.user


CurrentUser = Annotated[User, Depends(_current_user)]


def require_permission(permission: str) -> Callable[..., Coroutine[Any, Any, User]]:
    """Route-level check. The role is read from the database, never from the client or the token."""

    async def dep(user: CurrentUser, db: DB) -> User:
        if not has_permission(user.role, permission):
            raise Forbidden("missing_permission", "You do not have permission to do this.")
        if user.role in PRIVILEGED_ROLES:
            from app.modules.accounts import mfa

            if not await mfa.is_enabled(db, user.id):  # Blueprint 12.1: MFA mandatory for staff and admins
                raise Forbidden("mfa_setup_required", "Turn on two-factor login in Account before using staff tools.")
        return user

    return dep


def client_info(request: Request) -> ClientInfo:
    return ClientInfo(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


Client = Annotated[ClientInfo, Depends(client_info)]


async def optional_user(request: Request, db: AsyncSession) -> User | None:
    """The signed-in user for public pages that show more to members; None for visitors or bad tokens."""
    try:
        return (await _principal(request, db)).user
    except Unauthorized:
        return None
