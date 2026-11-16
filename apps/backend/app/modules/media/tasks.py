import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.media import service
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async


@celery_app.task(name="media.process", acks_late=True, ignore_result=True, time_limit=900, soft_time_limit=840)
def process_asset(asset_id: str) -> str:
    async def go(sm: async_sessionmaker[AsyncSession]) -> str:
        async with sm() as db:
            return await service.process(db, uuid.UUID(asset_id))

    return run_async(go)
