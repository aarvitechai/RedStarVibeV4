import uuid

from fastapi import APIRouter, Request

from app.api.deps import DB, CurrentUser, optional_user
from app.modules.accounts.schemas import OkOut
from app.modules.stories import service
from app.modules.stories.service import HighlightIn, HighlightOut, StoryCreate, StoryGroup, StoryOut

router = APIRouter(tags=["stories"])


@router.post("/stories", response_model=StoryOut, status_code=201)
async def create_story(body: StoryCreate, db: DB, user: CurrentUser) -> StoryOut:
    return await service.create(db, user, body)


@router.get("/stories/tray", response_model=list[StoryGroup])
async def tray(db: DB, user: CurrentUser) -> list[StoryGroup]:
    return await service.tray(db, user)


@router.post("/stories/{story_id}/view", response_model=OkOut)
async def view(story_id: uuid.UUID, db: DB, user: CurrentUser) -> OkOut:
    await service.view(db, user, story_id)
    return OkOut()


@router.get("/stories/{story_id}/viewers")
async def viewers(story_id: uuid.UUID, db: DB, user: CurrentUser) -> list[dict[str, str]]:
    return await service.viewers(db, user, story_id)


@router.post("/highlights", response_model=HighlightOut, status_code=201)
async def create_highlight(body: HighlightIn, db: DB, user: CurrentUser) -> HighlightOut:
    return await service.create_highlight(db, user, body)


@router.get("/profiles/{username}/highlights", response_model=list[HighlightOut])
async def highlights(username: str, request: Request, db: DB) -> list[HighlightOut]:
    return await service.highlights(db, await optional_user(request, db), username)
