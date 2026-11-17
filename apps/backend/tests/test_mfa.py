import time

import pytest
from httpx import AsyncClient

from app.core import totp
from tests.conftest import csrf, enable_mfa, signup
from tests.test_business_booking import new_client

pytestmark = pytest.mark.usefixtures("db")


def test_totp_matches_rfc6238_vector() -> None:
    # RFC 6238 appendix B, SHA-1, T = 59 s -> 94287082 (8 digits); our 6-digit code is the last 6 digits.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32("12345678901234567890")
    assert totp.code_at(secret, now=59) == "287082"
    assert totp.verify(secret, "287082", last_step=None, now=59) == 1
    assert totp.verify(secret, "287082", last_step=1, now=59) is None  # replay of the same step


async def login(c: AsyncClient, username: str) -> object:
    await csrf(c)
    return await c.post("/api/v1/auth/login", json={"email": f"{username}@example.com", "password": "Str0ng-Passw0rd!"})


async def test_login_requires_second_factor_and_blocks_replay(client: AsyncClient) -> None:
    await signup(client, username="secure_sana")
    secret = await enable_mfa(client)
    assert (await client.get("/api/v1/auth/mfa")).json() == {"enabled": True, "required": False}

    phone = new_client(client)
    r = await login(phone, "secure_sana")
    assert r.status_code == 401 and r.json()["error"]["code"] == "mfa_required"  # type: ignore[attr-defined]
    ticket = r.json()["error"]["details"]["ticket"]  # type: ignore[attr-defined]
    assert "rsv_at" not in phone.cookies  # no session before the second factor
    bad = await phone.post("/api/v1/auth/login/mfa", json={"ticket": ticket, "code": "000000"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "mfa_invalid_code"

    # Confirming used the current step, so log in with the next step's code (accepted within ±1 step of drift).
    code = totp.code_at(secret, now=time.time() + totp.STEP_S)
    ok = await phone.post("/api/v1/auth/login/mfa", json={"ticket": ticket, "code": code})
    assert ok.status_code == 200 and "rsv_at" in phone.cookies
    other = new_client(client)
    await csrf(other)
    replay = await other.post("/api/v1/auth/login/mfa", json={"ticket": ticket, "code": code})
    assert replay.status_code == 401 and replay.json()["error"]["code"] == "mfa_invalid_code"

    forged = await phone.post("/api/v1/auth/login/mfa", json={"ticket": "not-a-real-ticket", "code": "123456"})
    assert forged.status_code == 401 and forged.json()["error"]["code"] == "mfa_ticket_invalid"


async def test_cannot_enable_twice(client: AsyncClient) -> None:
    await signup(client, username="twice_tina")
    await enable_mfa(client)
    assert (await client.post("/api/v1/auth/mfa/setup")).status_code == 409
