"""AI gateway (Blueprint 20.7): per-user daily quota from the plan, a global daily budget switch, a circuit breaker,
and a log row for every call (feature, model, prompt version, latency, outcome, hashed user). AI suggests; users decide."""

import hashlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from redis.exceptions import RedisError
from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.providers import AIUnavailable, get_ai
from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.database import Base
from app.core.errors import RateLimited

log = logging.getLogger("rsv.ai")
T = TypeVar("T")
PROMPTS = Path(__file__).parent / "prompts"
BREAKER_FAILURES = 5
BREAKER_OPEN_S = 60
GLOBAL_DAILY_BUDGET_CALLS = 20_000


class AICall(Base):
    __tablename__ = "ai_calls"
    __table_args__ = {"schema": "ai"}  # noqa: RUF012
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_hash: Mapped[str] = mapped_column(String(16), nullable=False)
    feature: Mapped[str] = mapped_column(String(40), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)  # ok | fallback | error | quota
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def prompt(name: str) -> tuple[str, str]:
    """Versioned prompt files (caption_v1.md ...). Returns (version, text). Never inline long prompts in code."""
    path = PROMPTS / f"{name}.md"
    return name, path.read_text(encoding="utf-8")


def user_hash(user_id: uuid.UUID) -> str:
    return hashlib.sha256(f"{get_settings().secret_key}:{user_id}".encode()).hexdigest()[:16]


async def _quota(user_id: uuid.UUID, limit: int) -> None:
    day = datetime.now(UTC).strftime("%Y%m%d")
    try:
        redis = get_redis()
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(f"ai:q:{day}:{user_id}")
            pipe.expire(f"ai:q:{day}:{user_id}", 90_000, nx=True)
            pipe.incr(f"ai:global:{day}")
            pipe.expire(f"ai:global:{day}", 90_000, nx=True)
            used, _, total, _ = await pipe.execute()
    except RedisError:
        return
    if int(used) > limit:
        raise RateLimited(
            "ai_quota_exceeded", "You have used today's AI suggestions. They reset at midnight, or upgrade your plan."
        )
    if int(total) > GLOBAL_DAILY_BUDGET_CALLS:
        raise AIUnavailable("daily AI budget reached")  # budget switch: heavy features degrade, the app keeps working


async def _breaker_open() -> bool:
    try:
        return bool(await get_redis().exists("ai:breaker:open"))
    except RedisError:
        return False


async def _record_failure() -> None:
    try:
        redis = get_redis()
        n = await redis.incr("ai:breaker:fails")
        await redis.expire("ai:breaker:fails", BREAKER_OPEN_S)
        if int(n) >= BREAKER_FAILURES:
            await redis.set("ai:breaker:open", "1", ex=BREAKER_OPEN_S)
    except RedisError:
        pass


async def run(
    db: AsyncSession,
    user_id: uuid.UUID,
    daily_limit: int,
    feature: str,
    call: Callable[[], Awaitable[T]],
    fallback: Callable[[], T],
    prompt_version: str | None = None,
) -> tuple[T, str]:
    """Run an AI call with quota, breaker and logging. Returns (result, outcome). Provider down never means feature down."""
    started = time.monotonic()
    outcome = "ok"
    try:
        await _quota(user_id, daily_limit)
        if await _breaker_open():
            raise AIUnavailable("circuit open")
        result = await call()
    except RateLimited:
        db.add(
            AICall(
                user_hash=user_hash(user_id),
                feature=feature,
                provider=get_ai().name,
                prompt_version=prompt_version,
                latency_ms=0,
                outcome="quota",
            )
        )
        await db.commit()
        raise
    except AIUnavailable:
        result, outcome = fallback(), "fallback"
    except Exception:
        log.warning("ai_call_failed feature=%s", feature, exc_info=True)
        await _record_failure()
        result, outcome = fallback(), "error"
    db.add(
        AICall(
            user_hash=user_hash(user_id),
            feature=feature,
            provider=get_ai().name,
            prompt_version=prompt_version,
            latency_ms=int((time.monotonic() - started) * 1000),
            outcome=outcome,
        )
    )
    await db.commit()
    return result, outcome
