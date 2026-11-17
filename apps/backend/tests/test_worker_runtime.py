"""Phase 8: worker tasks reuse one event loop and DB pool per process.

Regression: with a new loop per task, the process-wide Redis client (app.core.cache) stayed bound to the first
task's closed loop, and later tasks failed with "Event loop is closed" (seen as a posts.published dead letter
under load). Sync test on purpose: Celery tasks run outside any event loop.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import cache
from app.workers import runtime


async def _touch(sm: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    await cache.get_redis().ping()  # the shared client must work in every task
    async with sm() as db:
        pid = await db.scalar(text("SELECT pg_backend_pid()"))
    return id(cache.get_redis()), int(pid or 0)


@pytest.fixture
def worker_process() -> Iterator[None]:
    """A fresh worker runtime. The shared Redis client is swapped out, because any client created by other tests
    is bound to pytest's loop, while this runtime's client must live on the worker loop."""
    saved = cache._redis
    cache._redis = None
    try:
        yield
    finally:
        runtime._close()
        cache._redis = saved
    assert runtime._state == {}


def test_tasks_share_one_loop_redis_client_and_pooled_connection(worker_process: None) -> None:
    results = [runtime.run_async(_touch) for _ in range(3)]
    assert len({r[0] for r in results}) == 1  # same Redis client, no "Event loop is closed"
    assert len({r[1] for r in results}) == 1  # same pooled DB connection, no reconnect per task


async def _timeouts(sm: async_sessionmaker[AsyncSession]) -> tuple[str, str]:
    async with sm() as db:
        row = (
            await db.execute(
                text("SELECT current_setting('statement_timeout'), current_setting('idle_in_transaction_session_timeout')")
            )
        ).one()
    return str(row[0]), str(row[1])


def test_worker_engine_has_the_same_query_timeouts_as_the_api(worker_process: None) -> None:
    """Before Phase 8 the worker built its own engine with no statement timeout."""
    assert runtime.run_async(_timeouts) == ("5s", "30s")


async def test_pgbouncer_mode_sets_timeouts_per_transaction_not_at_startup() -> None:
    """PgBouncer rejects statement_timeout as a startup parameter, so behind it the timeouts are set per transaction."""
    from app.core.config import get_settings
    from app.core.database import build_engine

    engine = build_engine(get_settings().model_copy(update={"db_pgbouncer": True}), pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as conn:
            raw = (await conn.get_raw_connection()).driver_connection
            assert raw is not None
            assert await raw.fetchval("SHOW statement_timeout") == "0"  # nothing was sent at connect time
            # Any app query autobegins a transaction, and the begin hook applies the limits to it.
            assert (await conn.execute(text("SELECT current_setting('statement_timeout')"))).scalar() == "5s"
            await conn.rollback()
            assert await raw.fetchval("SHOW statement_timeout") == "0"  # SET LOCAL ended with the transaction
    finally:
        await engine.dispose()
