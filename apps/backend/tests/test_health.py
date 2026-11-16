from httpx import AsyncClient

from app.api import health


async def test_live_is_ok(client: AsyncClient) -> None:
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["x-request-id"]


async def test_ready_reports_failed_dependencies(client: AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def boom() -> str:
        raise ConnectionError("down")

    async def fine() -> str:
        return "ok"

    monkeypatch.setattr(health, "_check_db", boom)
    monkeypatch.setattr(health, "_check_redis", fine)
    r = await client.get("/health/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "fail", "checks": {"database": "fail", "redis": "ok"}}


async def test_ready_ok_when_all_dependencies_ok(client: AsyncClient, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fine() -> str:
        return "ok"

    monkeypatch.setattr(health, "_check_db", fine)
    monkeypatch.setattr(health, "_check_redis", fine)
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
