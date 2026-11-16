"""Real-time fan-out over Redis pub/sub. Any process publishes; whichever ws replica holds the user's socket delivers.

Delivery is best effort: messages are persisted first and carry a per-conversation `seq`, so a client that
missed a frame catches up with GET .../messages?after_seq=N on reconnect (Blueprint 9.4).
"""

import json
import logging
import uuid
from typing import Any

from redis.exceptions import RedisError

from app.core.cache import get_redis

log = logging.getLogger("rsv.realtime")


def channel(user_id: uuid.UUID | str) -> str:
    return f"rt:u:{user_id}"


async def publish(user_ids: list[uuid.UUID], frame: dict[str, Any]) -> None:
    data = json.dumps(frame, default=str)
    try:
        async with get_redis().pipeline(transaction=False) as pipe:
            for uid in user_ids:
                pipe.publish(channel(uid), data)
            await pipe.execute()
    except RedisError:
        log.warning("realtime_publish_failed type=%s", frame.get("type"))
