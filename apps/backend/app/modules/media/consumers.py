"""media.uploaded -> hand off to the media queue (heavy work never runs in the dispatcher)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, consumer


@consumer("media.uploaded", name="media.enqueue_processing")
async def enqueue(db: AsyncSession, e: Event) -> None:
    from app.modules.media.tasks import process_asset

    process_asset.apply_async(args=[e.payload["asset_id"]], queue="media")
