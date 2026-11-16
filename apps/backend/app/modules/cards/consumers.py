from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, consumer


@consumer("cards.created", name="cards.enqueue_render")
async def enqueue_render(db: AsyncSession, e: Event) -> None:
    from app.modules.cards.tasks import render_card

    render_card.apply_async(args=[e.payload["card_id"]], queue="media")
