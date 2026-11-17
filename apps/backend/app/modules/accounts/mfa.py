"""Two-factor login with TOTP (Blueprint 12.1). Required for staff, admin and superadmin; optional for everyone else.

Login with MFA enabled: POST /auth/login -> 401 {code: "mfa_required", details: {ticket}} -> POST /auth/login/mfa
with the ticket (signed, 5 minutes) and a 6-digit code. Used codes cannot be replayed.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import segno
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, DateTime, LargeBinary, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core import crypto, rate_limit, totp
from app.core.config import get_settings
from app.core.database import Base
from app.core.errors import AppError, Conflict, Unauthorized
from app.modules.accounts.models import User
from app.modules.audit import service as audit

TICKET_TTL = timedelta(minutes=5)


class MfaFactor(Base):
    __tablename__ = "mfa_factors"
    __table_args__ = {"schema": "accounts"}  # noqa: RUF012
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    secret_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_step: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MfaSetupOut(BaseModel):
    otpauth_uri: str
    qr_svg: str
    secret: str


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class MfaLoginIn(BaseModel):
    ticket: str = Field(min_length=10, max_length=2000)
    code: str = Field(min_length=6, max_length=8)


class MfaStatus(BaseModel):
    enabled: bool
    required: bool


async def is_enabled(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return (
        await db.scalar(select(MfaFactor.user_id).where(MfaFactor.user_id == user_id, MfaFactor.confirmed_at.is_not(None)))
        is not None
    )


async def setup(db: AsyncSession, user: User) -> MfaSetupOut:
    if await is_enabled(db, user.id):
        raise Conflict("mfa_already_enabled", "Two-factor login is already on.")
    secret = totp.new_secret()
    factor = await db.get(MfaFactor, user.id)
    if factor is None:
        db.add(MfaFactor(user_id=user.id, secret_enc=crypto.encrypt(secret)))
    else:
        factor.secret_enc, factor.last_step = crypto.encrypt(secret) or b"", None
    await db.commit()
    uri = totp.provisioning_uri(secret, user.email)
    return MfaSetupOut(otpauth_uri=uri, qr_svg=segno.make(uri, error="m").svg_inline(scale=5), secret=secret)


async def _check(db: AsyncSession, factor: MfaFactor, code: str, user_id: uuid.UUID) -> None:
    await rate_limit.enforce("mfa_verify", str(user_id), limit=5, window_s=300)
    secret = crypto.decrypt(factor.secret_enc) or ""
    step = totp.verify(secret, code, factor.last_step)
    if step is None:
        raise Unauthorized("mfa_invalid_code", "That code is not right. Use the latest code from your authenticator app.")
    factor.last_step = step


async def confirm(db: AsyncSession, user: User, code: str, ip: str) -> MfaStatus:
    factor = await db.get(MfaFactor, user.id, with_for_update=True)
    if factor is None:
        raise AppError("mfa_not_started", "Start two-factor setup first.")
    await _check(db, factor, code, user.id)
    factor.confirmed_at = datetime.now(UTC)
    await audit.record(db, actor_id=user.id, action="mfa.enabled", target_type="user", target_id=str(user.id), ip=ip)
    await db.commit()
    return MfaStatus(enabled=True, required=user.role in ("staff", "admin", "superadmin"))


def issue_ticket(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "typ": "mfa", "iat": int(now.timestamp()), "exp": int((now + TICKET_TTL).timestamp())},
        get_settings().secret_key,
        algorithm="HS256",
    )


async def verify_ticket(db: AsyncSession, ticket: str, code: str) -> uuid.UUID:
    try:
        data = jwt.decode(ticket, get_settings().secret_key, algorithms=["HS256"], options={"require": ["exp", "sub", "typ"]})
    except jwt.PyJWTError as exc:
        raise Unauthorized("mfa_ticket_invalid", "Please log in again.") from exc
    if data.get("typ") != "mfa":
        raise Unauthorized("mfa_ticket_invalid", "Please log in again.")
    user_id = uuid.UUID(data["sub"])
    factor = await db.get(MfaFactor, user_id, with_for_update=True)
    if factor is None or factor.confirmed_at is None:
        raise Unauthorized("mfa_ticket_invalid", "Please log in again.")
    await _check(db, factor, code, user_id)
    return user_id
