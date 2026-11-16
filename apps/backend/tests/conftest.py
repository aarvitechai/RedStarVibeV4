"""Test setup.

Unit tests need nothing. Integration tests (fixture `db`) need a separate Postgres + Redis, never the app DB:
    RSV_TEST_DATABASE_URL (default postgresql+asyncpg://rsv:rsvtest@127.0.0.1:55432/rsv_test)
    RSV_TEST_REDIS_URL    (default redis://127.0.0.1:56379/15)
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

TEST_DB = os.environ.get("RSV_TEST_DATABASE_URL", "postgresql+asyncpg://rsv:rsvtest@127.0.0.1:55432/rsv_test")
TEST_REDIS = os.environ.get("RSV_TEST_REDIS_URL", "redis://127.0.0.1:56379/15")
os.environ["RSV_ENV"] = "test"
os.environ["RSV_DATABASE_URL"] = TEST_DB
os.environ["RSV_REDIS_URL"] = TEST_REDIS
os.environ.setdefault("RSV_SECRET_KEY", "test-secret-key-test-secret-key-0123456789")

from httpx import ASGITransport, AsyncClient  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent


# Reference data seeded by migrations; kept between tests.
SEED_TABLES = {"cards.templates", "shop.categories"}


def _all_tables() -> str:
    """Every table any module declares (except seed data), so new modules are cleaned automatically."""
    from app.models import Base

    names = (f"{t.schema}.{t.name}" for t in Base.metadata.sorted_tables)
    return ", ".join(n for n in names if n not in SEED_TABLES)


async def _db_reachable() -> bool:
    import asyncpg

    try:
        conn = await asyncpg.connect(TEST_DB.replace("+asyncpg", ""), timeout=3)
    except Exception:
        return False
    await conn.close()
    return True


async def _reset_schema() -> None:
    import asyncpg

    conn = await asyncpg.connect(TEST_DB.replace("+asyncpg", ""))
    try:
        schemas = await conn.fetch(
            "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname NOT IN "
            "('public', 'information_schema', 'tiger', 'tiger_data', 'topology')"
        )
        for row in schemas:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{row["nspname"]}" CASCADE')
        await conn.execute("DROP TABLE IF EXISTS public.alembic_version")
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def migrated_db() -> str:
    if not asyncio.run(_db_reachable()):
        pytest.skip("test database not reachable (see tests/conftest.py)")
    asyncio.run(_reset_schema())
    env = {**os.environ, "RSV_DATABASE_URL": TEST_DB}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)
    return TEST_DB


@pytest.fixture
async def db(migrated_db: str) -> AsyncIterator[Any]:
    """Clean tables and Redis before each integration test, and yield a session factory."""
    from sqlalchemy import text

    from app.core.cache import get_redis
    from app.core.database import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as s:
        await s.execute(text("SET LOCAL session_replication_role = replica"))  # this transaction only: bypass append-only trigger
        await s.execute(text(f"TRUNCATE {_all_tables()} RESTART IDENTITY CASCADE"))
        await s.commit()
    await get_redis().flushdb()
    from app.core.storage import MemoryStorage, set_storage_for_tests

    set_storage_for_tests(MemoryStorage())
    yield sm
    set_storage_for_tests(None)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def csrf(client: AsyncClient) -> None:
    """Fetch the CSRF cookie and send it back as the header on every later request."""
    r = await client.get("/api/v1/auth/csrf")
    client.headers["x-csrf-token"] = r.json()["csrf_token"]


async def signup(
    client: AsyncClient, username: str = "ravi_kumar", email: str | None = None, password: str = "Str0ng-Passw0rd!", **extra: Any
) -> Any:
    await csrf(client)
    body = {
        "username": username,
        "email": email or f"{username}@example.com",
        "password": password,
        "display_name": username.replace("_", " ").title(),
        "is_18_or_older": True,
        **extra,
    }
    return await client.post("/api/v1/auth/signup", json=body)
