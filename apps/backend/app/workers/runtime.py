"""Run async service code from sync Celery tasks.

Phase 8, Level 1: each worker *process* keeps one event loop and one small connection pool, reused across tasks.
Before, every task ran in a new loop with a NullPool engine, so every event paid for a new TCP connection, a
SCRAM login and asyncpg type introspection (82 reconnects in a 70 s load test; docs/capacity/2026-11-17-baseline.md).

Safe because a prefork child runs one task at a time, the state is rebuilt after fork (pid check), and
worker_max_tasks_per_child recycles the process (and so the pool) regularly.
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import TypeVar

from celery.signals import worker_process_shutdown
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.cache import close_redis
from app.core.config import get_settings
from app.core.database import build_engine

T = TypeVar("T")

_state: dict[str, object] = {}


def _runtime() -> tuple[asyncio.AbstractEventLoop, async_sessionmaker[AsyncSession]]:
    if _state.get("pid") != os.getpid():  # first task in this process (or a forked copy of a parent's state)
        loop = asyncio.new_event_loop()
        # Same recipe (timeouts, PgBouncer handling) as the API; a small pool since a child runs one task at a time.
        engine = build_engine(get_settings(), pool_size=2, max_overflow=2)
        _state.update(pid=os.getpid(), loop=loop, engine=engine, sm=async_sessionmaker(engine, expire_on_commit=False))
    return _state["loop"], _state["sm"]  # type: ignore[return-value]


def run_async(fn: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    loop, sm = _runtime()
    return loop.run_until_complete(fn(sm))


@worker_process_shutdown.connect
def _close(**_: object) -> None:
    """Close pooled DB connections and the shared Redis client (bound to this loop) when Celery retires the process."""
    if _state.get("pid") != os.getpid():
        return
    loop: asyncio.AbstractEventLoop = _state["loop"]  # type: ignore[assignment]
    engine: AsyncEngine = _state["engine"]  # type: ignore[assignment]
    loop.run_until_complete(engine.dispose())
    loop.run_until_complete(close_redis())
    loop.close()
    _state.clear()
