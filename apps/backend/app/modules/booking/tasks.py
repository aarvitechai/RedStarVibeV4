"""Beat jobs owned by booking: reminders (every minute) and expiry of unconfirmed bookings (every 5 minutes)."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.booking import service
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async


@celery_app.task(name="booking.send_reminders", ignore_result=True)
def send_reminders() -> int:
    async def go(sm: async_sessionmaker[AsyncSession]) -> int:
        async with sm() as db:
            return await service.send_reminders(db)

    return run_async(go)


@celery_app.task(name="booking.expire_stale", ignore_result=True)
def expire_stale() -> int:
    async def go(sm: async_sessionmaker[AsyncSession]) -> int:
        async with sm() as db:
            return await service.expire_stale(db)

    return run_async(go)
