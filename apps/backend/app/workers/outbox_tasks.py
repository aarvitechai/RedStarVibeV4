"""Outbox relay (beat, every 2 s) and the single event dispatcher (ADR 0011)."""

import logging
import random
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.events import MAX_ATTEMPTS, Event, dead_letter, dispatch_event, relay_once
from app.workers import consumers  # noqa: F401  - registers all consumers
from app.workers.celery_app import celery_app
from app.workers.runtime import run_async

log = logging.getLogger("rsv.outbox")


def _publish(message: dict[str, Any]) -> None:
    dispatch.apply_async(args=[message], queue="default")


@celery_app.task(name="outbox.relay", ignore_result=True)
def relay() -> int:
    async def go(sm: async_sessionmaker[AsyncSession]) -> int:
        async with sm() as session:
            return await relay_once(session, _publish)

    return run_async(go)


@celery_app.task(name="events.dispatch", bind=True, acks_late=True, max_retries=MAX_ATTEMPTS, ignore_result=True)
def dispatch(self: Any, message: dict[str, Any]) -> list[str]:
    event = Event.from_message(message)
    try:
        return run_async(lambda sm: dispatch_event(sm, event))
    except Exception as exc:
        error = repr(exc)
        if self.request.retries >= MAX_ATTEMPTS:
            log.error("event_dead_lettered type=%s event_id=%s", event.type, event.event_id)
            run_async(lambda sm: dead_letter(sm, event, "dispatch", error))
            return []
        # Exponential backoff with jitter: 2, 4, 8, 16, 32 s plus up to 1 s.
        countdown = 2 ** (self.request.retries + 1) + random.uniform(0, 1)  # noqa: S311 - not security sensitive
        raise self.retry(exc=exc, countdown=countdown) from exc
