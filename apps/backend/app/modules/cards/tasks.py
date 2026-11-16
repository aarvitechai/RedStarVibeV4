import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.cards import service
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async


@celery_app.task(name="cards.render", acks_late=True, ignore_result=True)
def render_card(card_id: str) -> str:
    async def go(sm: async_sessionmaker[AsyncSession]) -> str:
        async with sm() as db:
            return await service.render(db, uuid.UUID(card_id))

    return run_async(go)
