"""Home feed (Blueprint 9.2): hybrid fan-out.

- Normal authors: on `posts.published`, the post id is pushed into each follower's Redis sorted set
  `feed:{user_id}` (score = created_at epoch, trimmed to 800, 7-day TTL).
- Celebrities (> CELEBRITY_FOLLOWERS): no fan-out; their recent posts are merged at read time.
- Redis empty or down: rebuild from Postgres (followees' recent posts). Visibility and blocks filtered at read.
"""

import logging
import uuid
from datetime import UTC, datetime

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_redis
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.accounts.models import User
from app.modules.posts import service as posts
from app.modules.posts.models import Post
from app.modules.posts.service import PostPage
from app.modules.social import service as social

log = logging.getLogger("rsv.feed")
FEED_MAX = 800
FEED_TTL_S = 7 * 24 * 3600


def _key(user_id: uuid.UUID) -> str:
    return f"feed:{user_id}"


async def fan_out(db: AsyncSession, post_id: uuid.UUID, author_id: uuid.UUID, created_at: datetime) -> int:
    followers = await social.follower_ids(db, author_id)
    if len(followers) > social.CELEBRITY_FOLLOWERS:
        return 0  # merged at read time
    score = created_at.timestamp()
    redis = get_redis()
    try:
        for chunk_start in range(0, len(followers) + 1, 500):
            chunk = [author_id, *followers][chunk_start : chunk_start + 500]
            async with redis.pipeline(transaction=False) as pipe:
                for uid in chunk:
                    pipe.zadd(_key(uid), {str(post_id): score})
                    pipe.zremrangebyrank(_key(uid), 0, -FEED_MAX - 1)
                    pipe.expire(_key(uid), FEED_TTL_S)
                await pipe.execute()
    except RedisError:
        log.warning("feed_fanout_skipped post=%s (redis down; read path rebuilds from DB)", post_id)
        return 0
    return len(followers) + 1


async def remove(post_id: uuid.UUID, author_id: uuid.UUID, follower_ids: list[uuid.UUID]) -> None:
    try:
        async with get_redis().pipeline(transaction=False) as pipe:
            for uid in [author_id, *follower_ids]:
                pipe.zrem(_key(uid), str(post_id))
            await pipe.execute()
    except RedisError:
        pass


async def home(db: AsyncSession, viewer: User, cursor: str | None, limit: int) -> PostPage:
    c = decode_cursor(cursor)
    before = float(c["s"]) if c else None
    following = await social.following_ids(db, viewer.id)
    ids: list[uuid.UUID] = []
    try:
        max_score = f"({before}" if before is not None else "+inf"
        raw = await get_redis().zrevrangebyscore(_key(viewer.id), max_score, "-inf", start=0, num=limit * 2)
        ids = [uuid.UUID(str(x)) for x in raw]
    except RedisError:
        log.warning("feed_redis_unavailable; using database")
    rows: list[Post] = await posts.get_posts(db, ids) if ids else []
    if not ids:  # cold cache or Redis down
        rows = await posts.recent_by_authors(
            db, [viewer.id, *following], datetime.fromtimestamp(before, UTC) if before else None, limit * 2
        )
    # Merge celebrities (no fan-out) at read time.
    celebrities = [f for f in following if await social.follower_count(db, f) > social.CELEBRITY_FOLLOWERS]
    if celebrities:
        rows += await posts.recent_by_authors(db, celebrities, datetime.fromtimestamp(before, UTC) if before else None, limit)
    hidden = await social.hidden_ids_for(db, viewer.id)
    allowed = {viewer.id, *following}
    seen: set[uuid.UUID] = set()
    visible = []
    for p in sorted(rows, key=lambda p: p.created_at, reverse=True):
        if p.id in seen or p.author_id in hidden or p.author_id not in allowed:
            continue  # unfollowed or blocked since fan-out
        seen.add(p.id)
        visible.append(p)
    visible = visible[:limit]
    items = await posts.hydrate(db, visible, viewer)
    nxt = encode_cursor({"s": visible[-1].created_at.timestamp()}) if len(visible) == limit else None
    return PostPage(items=items, next_cursor=nxt)
