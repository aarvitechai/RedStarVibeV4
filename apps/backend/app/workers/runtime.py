"""Run async service code from sync Celery tasks.

Each task call gets its own event loop (asyncio.run), so the engine uses NullPool: pooled asyncpg connections
cannot be shared across event loops.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

T = TypeVar("T")


def run_async(fn: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]]) -> T:
    async def _main() -> T:
        settings = get_settings()
        connect_args = {"statement_cache_size": 0} if settings.db_pgbouncer else {}
        engine = create_async_engine(settings.database_url, poolclass=NullPool, connect_args=connect_args)
        try:
            return await fn(async_sessionmaker(engine, expire_on_commit=False))
        finally:
            await engine.dispose()

    return asyncio.run(_main())
