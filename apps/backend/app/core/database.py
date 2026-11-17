"""Async SQLAlchemy engine and session. Sessions are always closed by the dependency (no globals holding sessions)."""

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import Connection, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


IDLE_IN_TRANSACTION_TIMEOUT_MS = 30000


def build_engine(settings: Settings, pool_size: int | None = None, max_overflow: int | None = None) -> AsyncEngine:
    """One engine recipe for the API, ws, MCP and the workers, so every process gets the same timeouts."""
    timeouts = {
        "statement_timeout": str(settings.db_statement_timeout_ms),
        "idle_in_transaction_session_timeout": str(IDLE_IN_TRANSACTION_TIMEOUT_MS),
    }
    connect_args: dict[str, Any] = {"server_settings": {"timezone": "UTC"}, "timeout": 5}
    if settings.db_pgbouncer:
        # ADR 0002/0021: transaction pooling keeps no session state, so the timeouts are set per transaction
        # below (PgBouncer rejects them as startup parameters). Statement caches stay on unless the PgBouncer
        # is too old to track prepared statements.
        if not settings.db_pgbouncer_prepared_statements:
            connect_args["statement_cache_size"] = 0
            connect_args["prepared_statement_cache_size"] = 0
    else:
        connect_args["server_settings"].update(timeouts)
    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size if pool_size is None else pool_size,
        max_overflow=settings.db_max_overflow if max_overflow is None else max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=connect_args,
    )
    if settings.db_pgbouncer:

        @event.listens_for(engine.sync_engine, "begin")
        def _transaction_timeouts(conn: Connection) -> None:
            # is_local=true: the values end with this transaction, so nothing leaks to the next PgBouncer client.
            conn.exec_driver_sql(
                "SELECT set_config('statement_timeout', $1, true), set_config('idle_in_transaction_session_timeout', $2, true)",
                (timeouts["statement_timeout"], timeouts["idle_in_transaction_session_timeout"]),
            )

    return engine


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = build_engine(get_settings())
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine, _sessionmaker = None, None
