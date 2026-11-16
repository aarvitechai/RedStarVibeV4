"""Invite links, referral attribution and Star Points (Blueprint 26). Points are platform rewards, never cash."""

import secrets
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.referrals.models import PointsEntry, Referral, ReferralCode

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I confusion
REFERRER_POINTS = 30  # friend became active (first booking)
JOINING_BONUS = 20


class ReferralSummary(BaseModel):
    code: str
    link: str
    invited: int
    qualified: int
    points: int


async def code_for(db: AsyncSession, user_id: uuid.UUID) -> str:
    existing = await db.scalar(select(ReferralCode.code).where(ReferralCode.user_id == user_id))
    if existing:
        return str(existing)
    for _ in range(5):
        code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
        inserted = await db.scalar(
            insert(ReferralCode).values(user_id=user_id, code=code).on_conflict_do_nothing().returning(ReferralCode.code)
        )
        if inserted:
            await db.commit()
            return str(inserted)
        again = await db.scalar(select(ReferralCode.code).where(ReferralCode.user_id == user_id))
        if again:
            return str(again)
    raise RuntimeError("could not allocate referral code")


async def summary(db: AsyncSession, user_id: uuid.UUID) -> ReferralSummary:
    code = await code_for(db, user_id)
    invited = await db.scalar(select(func.count()).where(Referral.referrer_id == user_id)) or 0
    qualified = await db.scalar(select(func.count()).where(Referral.referrer_id == user_id, Referral.status == "qualified")) or 0
    points = await db.scalar(select(func.coalesce(func.sum(PointsEntry.delta), 0)).where(PointsEntry.user_id == user_id)) or 0
    link = f"{get_settings().public_base_url.rstrip('/')}/signup?ref={code}"
    return ReferralSummary(code=code, link=link, invited=int(invited), qualified=int(qualified), points=int(points))


async def attribute(db: AsyncSession, referee_id: uuid.UUID, code: str) -> bool:
    """Record who invited a new account. Self-referral and unknown codes are ignored silently."""
    referrer = await db.scalar(select(ReferralCode.user_id).where(ReferralCode.code == code.strip().upper()))
    if referrer is None or referrer == referee_id:
        return False
    inserted = await db.scalar(
        insert(Referral)
        .values(referee_id=referee_id, referrer_id=referrer, status="pending")
        .on_conflict_do_nothing()
        .returning(Referral.referee_id)
    )
    return inserted is not None


async def award(db: AsyncSession, user_id: uuid.UUID, delta: int, reason: str, ref_id: str) -> bool:
    inserted = await db.scalar(
        insert(PointsEntry)
        .values(user_id=user_id, delta=delta, reason=reason, ref_id=ref_id)
        .on_conflict_do_nothing(constraint="ux_points_once")
        .returning(PointsEntry.id)
    )
    return inserted is not None


async def qualify_on_first_action(db: AsyncSession, referee_id: uuid.UUID) -> bool:
    ref = await db.get(Referral, referee_id, with_for_update=True)
    if ref is None or ref.status != "pending":
        return False
    ref.status, ref.qualified_at = "qualified", datetime.now(UTC)
    await award(db, ref.referrer_id, REFERRER_POINTS, "referral_qualified", str(referee_id))
    await award(db, referee_id, JOINING_BONUS, "joining_bonus", str(referee_id))
    return True
