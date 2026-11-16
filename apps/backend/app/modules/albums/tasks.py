import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.events import Event, consumer
from app.modules.albums import service
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async


@celery_app.task(name="albums.render_slideshow", acks_late=True, ignore_result=True, time_limit=900)
def render_slideshow(album_id: str) -> str:
    async def go(sm: async_sessionmaker[AsyncSession]) -> str:
        async with sm() as db:
            return await service.render_slideshow(db, uuid.UUID(album_id))

    return run_async(go)


@consumer("albums.slideshow_requested", name="albums.enqueue_slideshow")
async def enqueue(db: AsyncSession, e: Event) -> None:
    render_slideshow.apply_async(args=[e.payload["album_id"]], queue="media")
