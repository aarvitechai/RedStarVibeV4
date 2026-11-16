"""Fixed-window rate limits in Redis (Blueprint 12.2). If Redis is down we fail open and log, so writes keep working."""

import logging

from redis.exceptions import RedisError

from app.core.cache import get_redis
from app.core.errors import RateLimited

log = logging.getLogger("rsv.rate_limit")


async def hit(bucket: str, key: str, limit: int, window_s: int) -> bool:
    """Count one hit. Returns True if the caller is still within the limit."""
    redis_key = f"rl:{bucket}:{key}"
    try:
        async with get_redis().pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_s, nx=True)
            count, _ = await pipe.execute()
    except RedisError:
        log.warning("rate_limit_unavailable bucket=%s", bucket)
        return True
    return int(count) <= limit


async def enforce(bucket: str, key: str, limit: int, window_s: int) -> None:
    if not await hit(bucket, key, limit, window_s):
        raise RateLimited(details={"retry_after_s": window_s})


async def reset(bucket: str, key: str) -> None:
    try:
        await get_redis().delete(f"rl:{bucket}:{key}")
    except RedisError:
        log.warning("rate_limit_unavailable bucket=%s", bucket)
