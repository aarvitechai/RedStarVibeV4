"""Transactional outbox (ADR 0011).

`emit()` writes the event in the caller's transaction, so the event exists if and only if the business change
committed. The beat-driven relay publishes pending rows; `dispatch_event()` runs every registered consumer
at most once per event (processed_events table), so redelivery is harmless.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.ids import uuid7

log = logging.getLogger("rsv.events")

MAX_ATTEMPTS = 5


class OutboxEvent(Base):
    __tablename__ = "outbox"
    __table_args__ = {"schema": "notify"}  # noqa: RUF012

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    __table_args__ = {"schema": "notify"}  # noqa: RUF012

    consumer: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DeadLetter(Base):
    __tablename__ = "dead_letter"
    __table_args__ = {"schema": "notify"}  # noqa: RUF012

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    consumer: Mapped[str | None] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


@dataclass(frozen=True)
class Event:
    event_id: uuid.UUID
    type: str
    version: int
    payload: dict[str, Any]
    occurred_at: datetime

    def to_message(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "type": self.type,
            "version": self.version,
            "payload": self.payload,
            "occurred_at": self.occurred_at.isoformat(),
        }

    @classmethod
    def from_message(cls, m: dict[str, Any]) -> "Event":
        return cls(uuid.UUID(m["event_id"]), m["type"], int(m["version"]), m["payload"], datetime.fromisoformat(m["occurred_at"]))


def emit(session: AsyncSession, type: str, payload: dict[str, Any], version: int = 1) -> uuid.UUID:
    """Queue an event inside the caller's transaction. Names are `module.action`, e.g. `booking.created`."""
    event_id = uuid7()
    session.add(OutboxEvent(event_id=event_id, type=type, version=version, payload=payload, attempts=0))
    return event_id


Handler = Callable[[AsyncSession, Event], Awaitable[None]]


@dataclass
class _Registry:
    consumers: dict[str, list[tuple[str, Handler]]] = field(default_factory=dict)


_registry = _Registry()


def consumer(event_type: str, name: str) -> Callable[[Handler], Handler]:
    """Register an idempotent consumer. `name` must be stable: it keys the processed_events record."""

    def wrap(fn: Handler) -> Handler:
        entries = _registry.consumers.setdefault(event_type, [])
        if all(existing != name for existing, _ in entries):
            entries.append((name, fn))
        return fn

    return wrap


def consumers_for(event_type: str) -> list[tuple[str, Handler]]:
    return list(_registry.consumers.get(event_type, []))


async def relay_once(session: AsyncSession, publish: Callable[[dict[str, Any]], None], batch: int = 100) -> int:
    """Publish pending outbox rows. Rows are locked with SKIP LOCKED so two relays never double-publish."""
    rows = (
        await session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None), OutboxEvent.attempts < MAX_ATTEMPTS)
            .order_by(OutboxEvent.id)
            .limit(batch)
            .with_for_update(skip_locked=True)
        )
    ).all()
    published = 0
    for row in rows:
        event = Event(row.event_id, row.type, row.version, row.payload, row.created_at)
        try:
            publish(event.to_message())
        except Exception as exc:
            row.attempts += 1
            row.last_error = repr(exc)[:500]
            if row.attempts >= MAX_ATTEMPTS:
                session.add(
                    DeadLetter(event_id=row.event_id, consumer=None, type=row.type, payload=row.payload, error=row.last_error)
                )
            continue
        row.published_at = datetime.now(UTC)
        published += 1
    await session.commit()
    return published


async def dispatch_event(sessionmaker: async_sessionmaker[AsyncSession], event: Event) -> list[str]:
    """Run each consumer once. Each consumer commits with its processed-event marker in one transaction."""
    ran: list[str] = []
    for name, handler in consumers_for(event.type):
        async with sessionmaker() as session, session.begin():
            inserted = await session.scalar(
                insert(ProcessedEvent)
                .values(consumer=name, event_id=event.event_id)
                .on_conflict_do_nothing()
                .returning(ProcessedEvent.consumer)
            )
            if inserted is None:
                continue  # already processed
            await handler(session, event)
        ran.append(name)
    return ran


async def dead_letter(sessionmaker: async_sessionmaker[AsyncSession], event: Event, consumer_name: str, error: str) -> None:
    async with sessionmaker() as session, session.begin():
        session.add(
            DeadLetter(
                event_id=event.event_id, consumer=consumer_name, type=event.type, payload=event.payload, error=error[:2000]
            )
        )
