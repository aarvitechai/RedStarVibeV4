import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.events import DeadLetter, Event, OutboxEvent, consumer, dispatch_event, emit, relay_once
from app.core.permissions import has_permission
from app.modules.audit.models import AuditLog
from tests.conftest import enable_mfa, signup

pytestmark = pytest.mark.usefixtures("db")


async def _make_role(db, username: str, role: str) -> None:  # type: ignore[no-untyped-def]
    async with db() as s:
        await s.execute(text("UPDATE accounts.users SET role = :r WHERE username = :u"), {"r": role, "u": username})
        await s.commit()


def test_permission_map() -> None:
    assert has_permission("superadmin", "anything:at_all")
    assert has_permission("admin", "audit:read")
    assert not has_permission("user", "audit:read")
    assert not has_permission("admin", "user:role")
    assert not has_permission("unknown-role", "post:write")


async def test_user_cannot_read_audit_log_but_admin_can(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    await signup(client, username="asha")
    r = await client.get("/api/v1/admin/audit-log")
    assert r.status_code == 403 and r.json()["error"]["code"] == "missing_permission"
    # The role comes from the database, so the same token gains access once promoted.
    await _make_role(db, "asha", "admin")
    r = await client.get("/api/v1/admin/audit-log")
    assert r.status_code == 403 and r.json()["error"]["code"] == "mfa_setup_required"  # admins must use 2FA
    await enable_mfa(client)
    assert (await client.get("/api/v1/admin/audit-log")).status_code == 200


async def test_role_change_by_superadmin_is_audited(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    target = AsyncClient(transport=client._transport, base_url="http://test")  # type: ignore[attr-defined]
    target_id = (await signup(target, username="mohan")).json()["id"]
    await signup(client, username="boss")
    await _make_role(db, "boss", "superadmin")
    await enable_mfa(client)

    r = await client.patch(f"/api/v1/admin/users/{target_id}/role", json={"role": "staff"})
    assert r.status_code == 200 and r.json()["role"] == "staff"
    page = (await client.get("/api/v1/admin/audit-log")).json()
    actions = [e["action"] for e in page["items"]]
    assert "user.role_changed" in actions
    entry = next(e for e in page["items"] if e["action"] == "user.role_changed")
    assert entry["details"] == {"from": "user", "to": "staff"} and entry["target_id"] == target_id

    # Nobody can mint a superadmin through the API.
    r = await client.patch(f"/api/v1/admin/users/{target_id}/role", json={"role": "superadmin"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "superadmin_via_script"


async def test_admin_cannot_change_roles(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    await signup(client, username="adminuser")
    await _make_role(db, "adminuser", "admin")
    r = await client.patch(f"/api/v1/admin/users/{uuid.uuid4()}/role", json={"role": "admin"})
    assert r.status_code == 403


async def test_audit_log_is_append_only(db) -> None:  # type: ignore[no-untyped-def]
    async with db() as s:
        s.add(AuditLog(actor_id=None, action="test", target_type="t", target_id="1", details={}))
        await s.commit()
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("UPDATE accounts.audit_log SET action = 'tampered'"))
        await s.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            await s.execute(text("DELETE FROM accounts.audit_log"))


async def test_emit_rolls_back_with_the_business_change(db) -> None:  # type: ignore[no-untyped-def]
    async with db() as s:
        emit(s, "test.happened", {"n": 1})
        await s.rollback()
        assert (await s.scalars(select(OutboxEvent))).all() == []
        emit(s, "test.happened", {"n": 2})
        await s.commit()
        assert [e.payload for e in (await s.scalars(select(OutboxEvent))).all()] == [{"n": 2}]


async def test_relay_publishes_once_and_dead_letters_after_retries(db) -> None:  # type: ignore[no-untyped-def]
    async with db() as s:
        emit(s, "test.ok", {})
        emit(s, "test.broken", {})
        await s.commit()

    sent: list[str] = []

    def publish(message: dict) -> None:  # type: ignore[type-arg]
        if message["type"] == "test.broken":
            raise ConnectionError("broker down")
        sent.append(message["type"])

    for _ in range(6):
        async with db() as s:
            await relay_once(s, publish)
    assert sent == ["test.ok"]  # published exactly once
    async with db() as s:
        dead = (await s.scalars(select(DeadLetter))).all()
    assert [d.type for d in dead] == ["test.broken"]


calls: list[uuid.UUID] = []


@consumer("test.counted", name="tests.counter")
async def _counter(_db, event: Event) -> None:  # type: ignore[no-untyped-def]
    calls.append(event.event_id)


async def test_dispatch_is_idempotent(db) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    calls.clear()
    event = Event(uuid.uuid4(), "test.counted", 1, {}, datetime.now(UTC))
    assert await dispatch_event(db, event) == ["tests.counter"]
    assert await dispatch_event(db, event) == []  # redelivery does nothing
    assert calls == [event.event_id]


async def test_signup_consumer_writes_audit(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    import app.workers.consumers  # noqa: F401

    await signup(client, username="kavya")
    async with db() as s:
        row = await s.scalar(select(OutboxEvent))
    assert row is not None
    await dispatch_event(db, Event(row.event_id, row.type, row.version, row.payload, row.created_at))
    async with db() as s:
        actions = (await s.scalars(select(AuditLog.action))).all()
    assert actions == ["user.signed_up"]
