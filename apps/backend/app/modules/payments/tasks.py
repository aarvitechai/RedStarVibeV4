from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.payments import service
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async


@celery_app.task(name="payments.reconcile", ignore_result=True)
def reconcile() -> int:
    async def go(sm: async_sessionmaker[AsyncSession]) -> int:
        async with sm() as db:
            return await service.reconcile(db)

    return run_async(go)
