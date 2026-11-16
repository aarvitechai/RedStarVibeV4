import uuid

from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.modules.calls import service
from app.modules.calls.service import CallToken

router = APIRouter(prefix="/calls", tags=["calls"])


@router.post("/{conversation_id}/token", response_model=CallToken)
async def call_token(conversation_id: uuid.UUID, db: DB, user: CurrentUser, ring: bool = True) -> CallToken:
    """Short-lived LiveKit token. `ring=false` when answering (does not ring the others again)."""
    return await service.token_for(db, user, conversation_id, ring)
