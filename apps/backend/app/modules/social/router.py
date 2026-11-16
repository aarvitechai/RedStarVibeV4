from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.deps import DB, CurrentUser, optional_user
from app.modules.accounts.schemas import OkOut
from app.modules.social import service
from app.modules.social.service import ProfileOut, ProfileUpdate, UserCard

router = APIRouter(tags=["social"])


@router.get("/profiles/{username}", response_model=ProfileOut)
async def get_profile(username: str, request: Request, db: DB) -> ProfileOut:
    return await service.profile(db, await optional_user(request, db), username)


@router.patch("/profiles/me", response_model=ProfileOut)
async def update_profile(body: ProfileUpdate, db: DB, user: CurrentUser) -> ProfileOut:
    return await service.update_profile(db, user, body)


@router.post("/profiles/{username}/follow")
async def follow(username: str, db: DB, user: CurrentUser) -> dict[str, str]:
    return {"status": await service.follow(db, user, username)}


@router.delete("/profiles/{username}/follow", response_model=OkOut)
async def unfollow(username: str, db: DB, user: CurrentUser) -> OkOut:
    await service.unfollow(db, user, username)
    return OkOut()


@router.get("/follow-requests", response_model=list[UserCard])
async def follow_requests(db: DB, user: CurrentUser) -> list[UserCard]:
    return await service.pending_requests(db, user)


@router.post("/follow-requests/{username}/{decision}", response_model=OkOut)
async def answer(username: str, decision: str, db: DB, user: CurrentUser) -> OkOut:
    await service.answer_request(db, user, username, approve=decision == "approve")
    return OkOut()


@router.post("/profiles/{username}/block", response_model=OkOut)
async def block(username: str, db: DB, user: CurrentUser) -> OkOut:
    await service.block(db, user, username)
    return OkOut()


@router.delete("/profiles/{username}/block", response_model=OkOut)
async def unblock(username: str, db: DB, user: CurrentUser) -> OkOut:
    await service.unblock(db, user, username)
    return OkOut()


@router.post("/profiles/{username}/mute", response_model=OkOut)
async def mute(username: str, db: DB, user: CurrentUser) -> OkOut:
    await service.mute(db, user, username, on=True)
    return OkOut()


@router.delete("/profiles/{username}/mute", response_model=OkOut)
async def unmute(username: str, db: DB, user: CurrentUser) -> OkOut:
    await service.mute(db, user, username, on=False)
    return OkOut()


@router.get("/search/users", response_model=list[UserCard])
async def search_users(request: Request, db: DB, q: Annotated[str, Query(min_length=1, max_length=40)]) -> list[UserCard]:
    return await service.search_users(db, await optional_user(request, db), q)
