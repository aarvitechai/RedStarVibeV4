"""Audio/video calls with LiveKit (Blueprint 10, Phase 7). The API never touches media: it only issues short-lived
room tokens after membership, block and privacy checks, and rings the other members over WebSocket."""

import time
import uuid
from typing import Any

import jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import get_settings
from app.core.errors import AppError, Forbidden
from app.modules.accounts.models import User
from app.modules.chat import service as chat
from app.modules.social import service as social
from app.realtime import hub

TOKEN_TTL_S = 300  # 5 minutes
MAX_GROUP_PARTICIPANTS = 8


class CallToken(BaseModel):
    url: str
    token: str
    room: str
    expires_in_s: int


def livekit_token(room: str, identity: str, name: str, now: int | None = None) -> str:
    s = get_settings()
    now = now or int(time.time())
    claims: dict[str, Any] = {
        "iss": s.livekit_api_key,
        "sub": identity,
        "name": name,
        "nbf": now - 5,
        "exp": now + TOKEN_TTL_S,
        "video": {"room": room, "roomJoin": True, "canPublish": True, "canSubscribe": True, "canPublishData": True},
    }
    return jwt.encode(claims, s.livekit_api_secret, algorithm="HS256")


async def token_for(db: AsyncSession, user: User, conversation_id: uuid.UUID, ring: bool) -> CallToken:
    s = get_settings()
    if not (s.livekit_url and s.livekit_api_key and s.livekit_api_secret):
        raise AppError("calls_unavailable", "Calling is not configured yet.")
    members = await chat.call_members(db, user, conversation_id)  # 404 unless the caller is a member
    others = [m for m in members if m != user.id]
    if len(members) > MAX_GROUP_PARTICIPANTS:
        raise AppError("call_too_large", f"Group calls support up to {MAX_GROUP_PARTICIPANTS} people.")
    for other in others:
        if await social.blocked_between(db, user.id, other):
            raise Forbidden("blocked", "You cannot call this account.")
    await rate_limit.enforce("call_token", str(user.id), limit=30, window_s=600)
    room = f"conv-{conversation_id}"
    if ring:
        await hub.publish(
            others,
            {"type": "call.ringing", "conversation_id": str(conversation_id), "from": user.display_name, "from_id": str(user.id)},
        )
    return CallToken(
        url=s.livekit_url, token=livekit_token(room, str(user.id), user.display_name), room=room, expires_in_s=TOKEN_TTL_S
    )
