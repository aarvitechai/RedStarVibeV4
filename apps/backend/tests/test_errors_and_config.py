import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.config import Settings


async def test_unknown_route_uses_standard_error_shape(client: AsyncClient) -> None:
    r = await client.get("/api/v1/does-not-exist", headers={"x-request-id": "abc-123"})
    assert r.status_code == 404
    body = r.json()
    assert body == {"error": {"code": "not_found", "message": "Not Found", "details": {}, "request_id": "abc-123"}}


async def test_unsafe_request_id_is_replaced(client: AsyncClient) -> None:
    r = await client.get("/health/live", headers={"x-request-id": "bad id\nwith newline"})
    assert r.headers["x-request-id"] != "bad id\nwith newline"
    assert len(r.headers["x-request-id"]) == 32


async def test_meta(client: AsyncClient) -> None:
    r = await client.get("/api/v1/meta")
    assert r.status_code == 200
    assert r.json()["name"] == "RedStarVibe"


def test_production_refuses_weak_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(env="production", secret_key="change-me", field_encryption_key="x" * 40)


def test_production_accepts_strong_secrets() -> None:
    s = Settings(env="production", secret_key="k" * 48, field_encryption_key="e" * 48)
    assert s.is_deployed


def test_local_allows_default_secrets() -> None:
    assert Settings(env="local", secret_key="change-me").secret_key == "change-me"
