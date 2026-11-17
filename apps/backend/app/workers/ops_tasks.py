"""Operational gauges sampled by beat every 15 s: outbox lag, dead letters, queue depth.

The worker writes them to Redis (`ops:gauges`); the api's /metrics reads them back, so Prometheus scrapes one place.
"""

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async

GAUGES_KEY = "ops:gauges"


@celery_app.task(name="ops.sample_gauges", ignore_result=True)
def sample_gauges() -> dict[str, float]:
    async def go(sm: async_sessionmaker[AsyncSession]) -> dict[str, float]:
        async with sm() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT count(*) AS n, coalesce(extract(epoch FROM now() - min(created_at)), 0) AS oldest "
                        "FROM notify.outbox WHERE published_at IS NULL"
                    )
                )
            ).one()
            dead = await db.scalar(text("SELECT count(*) FROM notify.dead_letter"))
        out = {"outbox_pending": float(row.n), "outbox_oldest_s": float(row.oldest), "dead_letters": float(dead or 0)}
        redis = Redis.from_url(get_settings().redis_url, decode_responses=True)  # own client: this runs in a fresh event loop
        try:
            for q in ("default", "media", "ai"):
                out[f"queue_{q}"] = float(await redis.llen(q))
            await redis.hset(GAUGES_KEY, mapping={k: str(v) for k, v in out.items()})
            await redis.expire(GAUGES_KEY, 120)  # stale data disappears instead of looking healthy
        finally:
            await redis.aclose()
        return out

    return run_async(go)
