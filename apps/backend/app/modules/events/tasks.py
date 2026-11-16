from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.events import service
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async


@celery_app.task(name="events.expire_holds", ignore_result=True)
def expire_holds() -> int:
    async def go(sm: async_sessionmaker[AsyncSession]) -> int:
        async with sm() as db:
            return await service.expire_holds(db)

    return run_async(go)
