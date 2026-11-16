import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.events import OutboxEvent
from tests.conftest import csrf, signup

pytestmark = pytest.mark.usefixtures("db")


async def test_signup_sets_cookies_and_emits_event_in_same_transaction(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    r = await signup(client)
    assert r.status_code == 201, r.text
    assert r.json()["username"] == "ravi_kumar"
    assert r.json()["role"] == "user"
    assert "rsv_at" in client.cookies and "rsv_rt" in client.cookies
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "ravi_kumar@example.com"
    async with db() as s:
        types = (await s.scalars(select(OutboxEvent.type))).all()
    assert types == ["accounts.user_signed_up"]


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"username": "admin"}, "reserved"),
        ({"password": "short"}, "at least 10"),
        ({"is_18_or_older": False}, "18 or older"),
        ({"password": "ravi_kumar-secret"}, "less common"),
        ({"username": "a"}, "at least 3"),
    ],
)
async def test_signup_validation(client: AsyncClient, override: dict, fragment: str) -> None:  # type: ignore[type-arg]
    await csrf(client)
    body = {
        "username": "ravi_kumar",
        "email": "r@example.com",
        "password": "Str0ng-Passw0rd!",
        "display_name": "Ravi",
        "is_18_or_older": True,
        **override,
    }
    r = await client.post("/api/v1/auth/signup", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert fragment in r.text


async def test_duplicate_username_and_email_conflict(client: AsyncClient) -> None:
    assert (await signup(client)).status_code == 201
    other = AsyncClient(transport=client._transport, base_url="http://test")  # type: ignore[attr-defined]
    r = await signup(other, username="ravi_kumar", email="new@example.com")
    assert r.status_code == 409 and r.json()["error"]["code"] == "username_taken"
    r = await signup(other, username="someone_else", email="RAVI_KUMAR@example.com")
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"


async def test_mutation_without_csrf_is_rejected(client: AsyncClient) -> None:
    r = await client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "whatever"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"
    assert r.json()["error"]["request_id"] != "-"


async def test_login_wrong_password_then_rate_limited(client: AsyncClient) -> None:
    await signup(client)
    client.cookies.clear()
    await csrf(client)
    for _ in range(5):
        r = await client.post("/api/v1/auth/login", json={"email": "ravi_kumar@example.com", "password": "wrong-password"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "invalid_credentials"
    r = await client.post("/api/v1/auth/login", json={"email": "ravi_kumar@example.com", "password": "Str0ng-Passw0rd!"})
    assert r.status_code == 429


async def test_login_success(client: AsyncClient) -> None:
    await signup(client)
    client.cookies.clear()
    await csrf(client)
    r = await client.post("/api/v1/auth/login", json={"email": "RAVI_KUMAR@example.com", "password": "Str0ng-Passw0rd!"})
    assert r.status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_refresh_rotates_and_reuse_revokes_family(client: AsyncClient) -> None:
    await signup(client)
    old_refresh = client.cookies["rsv_rt"]
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    new_refresh = client.cookies["rsv_rt"]
    assert new_refresh != old_refresh

    # An attacker replays the old refresh token.
    attacker = AsyncClient(transport=client._transport, base_url="http://test")  # type: ignore[attr-defined]
    attacker.cookies.set("rsv_rt", old_refresh)
    attacker.cookies.set("rsv_csrf", "t")
    attacker.headers["x-csrf-token"] = "t"
    r = await attacker.post("/api/v1/auth/refresh")
    assert r.status_code == 401 and r.json()["error"]["code"] == "refresh_reused"

    # The whole family is revoked: the legitimate session is signed out too.
    assert (await client.get("/api/v1/auth/me")).json()["error"]["code"] == "session_revoked"
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_revokes_access_immediately(client: AsyncClient) -> None:
    await signup(client)
    access = client.cookies["rsv_at"]
    assert (await client.post("/api/v1/auth/logout")).status_code == 200
    client.cookies.set("rsv_at", access)  # reuse the old access token
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "session_revoked"


async def test_logout_other_devices(client: AsyncClient) -> None:
    await signup(client)
    phone = AsyncClient(transport=client._transport, base_url="http://test")  # type: ignore[attr-defined]
    await csrf(phone)
    await phone.post("/api/v1/auth/login", json={"email": "ravi_kumar@example.com", "password": "Str0ng-Passw0rd!"})
    sessions = (await client.get("/api/v1/auth/sessions")).json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    assert (await client.post("/api/v1/auth/sessions/logout-others")).status_code == 200
    assert (await phone.get("/api/v1/auth/me")).status_code == 401
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_unauthenticated_and_tampered_tokens(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).json()["error"]["code"] == "not_signed_in"
    client.cookies.set("rsv_at", "not-a-jwt")
    assert (await client.get("/api/v1/auth/me")).json()["error"]["code"] == "token_invalid"


async def test_password_is_hashed_with_argon2id(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    await signup(client)
    async with db() as s:
        h = await s.scalar(text("SELECT password_hash FROM accounts.users"))
    assert h.startswith("$argon2id$")
