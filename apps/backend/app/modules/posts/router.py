import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.deps import DB, CurrentUser, optional_user
from app.modules.accounts.schemas import OkOut
from app.modules.posts import feed, service
from app.modules.posts.service import CommentIn, CommentOut, PostCreate, PostOut, PostPage

router = APIRouter(tags=["posts"])
Limit = Annotated[int, Query(ge=1, le=50)]


@router.post("/posts", response_model=PostOut, status_code=201)
async def create_post(body: PostCreate, db: DB, user: CurrentUser) -> PostOut:
    return await service.create(db, user, body)


@router.get("/feed", response_model=PostPage)
async def home_feed(db: DB, user: CurrentUser, cursor: str | None = None, limit: Limit = 20) -> PostPage:
    return await feed.home(db, user, cursor, limit)


@router.get("/reels", response_model=PostPage)
async def reels(request: Request, db: DB, cursor: str | None = None, limit: Limit = 10) -> PostPage:
    return await service.reels(db, await optional_user(request, db), cursor, limit)


@router.get("/posts/saved", response_model=list[PostOut])
async def saved(db: DB, user: CurrentUser) -> list[PostOut]:
    return await service.saved(db, user)


@router.get("/posts/{post_id}", response_model=PostOut)
async def get_post(post_id: uuid.UUID, request: Request, db: DB) -> PostOut:
    viewer = await optional_user(request, db)
    return (await service.hydrate(db, [await service.visible_post(db, viewer, post_id)], viewer))[0]


@router.delete("/posts/{post_id}", response_model=OkOut)
async def delete_post(post_id: uuid.UUID, db: DB, user: CurrentUser) -> OkOut:
    await service.delete(db, user, post_id)
    return OkOut()


@router.post("/posts/{post_id}/like")
async def like(post_id: uuid.UUID, db: DB, user: CurrentUser) -> dict[str, int]:
    return {"like_count": await service.like(db, user, post_id, on=True)}


@router.delete("/posts/{post_id}/like")
async def unlike(post_id: uuid.UUID, db: DB, user: CurrentUser) -> dict[str, int]:
    return {"like_count": await service.like(db, user, post_id, on=False)}


@router.post("/posts/{post_id}/save", response_model=OkOut)
async def save(post_id: uuid.UUID, db: DB, user: CurrentUser) -> OkOut:
    await service.save(db, user, post_id, on=True)
    return OkOut()


@router.delete("/posts/{post_id}/save", response_model=OkOut)
async def unsave(post_id: uuid.UUID, db: DB, user: CurrentUser) -> OkOut:
    await service.save(db, user, post_id, on=False)
    return OkOut()


@router.get("/posts/{post_id}/comments", response_model=list[CommentOut])
async def list_comments(post_id: uuid.UUID, request: Request, db: DB) -> list[CommentOut]:
    return await service.comments(db, await optional_user(request, db), post_id)


@router.post("/posts/{post_id}/comments", response_model=CommentOut, status_code=201)
async def add_comment(post_id: uuid.UUID, body: CommentIn, db: DB, user: CurrentUser) -> CommentOut:
    return await service.add_comment(db, user, post_id, body)


@router.delete("/comments/{comment_id}", response_model=OkOut)
async def delete_comment(comment_id: uuid.UUID, db: DB, user: CurrentUser) -> OkOut:
    await service.delete_comment(db, user, comment_id)
    return OkOut()


@router.get("/profiles/{username}/posts", response_model=PostPage)
async def author_posts(username: str, request: Request, db: DB, cursor: str | None = None, limit: Limit = 20) -> PostPage:
    return await service.by_author(db, await optional_user(request, db), username, cursor, limit)


@router.get("/hashtags/{tag}", response_model=PostPage)
async def hashtag(tag: str, request: Request, db: DB, cursor: str | None = None, limit: Limit = 20) -> PostPage:
    return await service.by_hashtag(db, await optional_user(request, db), tag, cursor, limit)
