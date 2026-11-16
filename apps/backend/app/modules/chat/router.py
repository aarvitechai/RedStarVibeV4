import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import DB, CurrentUser
from app.modules.accounts.schemas import OkOut
from app.modules.chat import service
from app.modules.chat.service import ConversationOut, GroupIn, MessageIn, MessageOut

router = APIRouter(prefix="/chat", tags=["chat"])


class ReadIn(BaseModel):
    seq: int


@router.get("/conversations", response_model=list[ConversationOut])
async def conversations(db: DB, user: CurrentUser) -> list[ConversationOut]:
    return await service.conversations(db, user)


@router.post("/direct/{username}", response_model=ConversationOut)
async def direct(username: str, db: DB, user: CurrentUser) -> ConversationOut:
    return await service.direct(db, user, username)


@router.post("/groups", response_model=ConversationOut, status_code=201)
async def create_group(body: GroupIn, db: DB, user: CurrentUser) -> ConversationOut:
    return await service.create_group(db, user, body)


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageOut])
async def messages(
    conv_id: uuid.UUID,
    db: DB,
    user: CurrentUser,
    after_seq: Annotated[int | None, Query(ge=0, description="Reconnect catch-up: everything after this seq")] = None,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[MessageOut]:
    return await service.messages(db, user, conv_id, after_seq, before_seq, limit)


@router.post("/conversations/{conv_id}/messages", response_model=MessageOut, status_code=201)
async def send(conv_id: uuid.UUID, body: MessageIn, db: DB, user: CurrentUser) -> MessageOut:
    return await service.send(db, user, conv_id, body)


@router.post("/conversations/{conv_id}/read", response_model=OkOut)
async def read(conv_id: uuid.UUID, body: ReadIn, db: DB, user: CurrentUser) -> OkOut:
    await service.mark_read(db, user, conv_id, body.seq)
    return OkOut()


@router.post("/conversations/{conv_id}/typing", response_model=OkOut)
async def typing(conv_id: uuid.UUID, db: DB, user: CurrentUser) -> OkOut:
    await service.typing(db, user, conv_id)
    return OkOut()


@router.post("/conversations/{conv_id}/leave", response_model=OkOut)
async def leave(conv_id: uuid.UUID, db: DB, user: CurrentUser) -> OkOut:
    await service.leave(db, user, conv_id)
    return OkOut()


@router.delete("/conversations/{conv_id}/members/{username}", response_model=OkOut)
async def remove_member(conv_id: uuid.UUID, username: str, db: DB, user: CurrentUser) -> OkOut:
    await service.remove_member(db, user, conv_id, username)
    return OkOut()
