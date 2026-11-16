import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.payments import service as payments
from app.modules.payments.providers import SandboxProvider
from app.modules.payments.service import LedgerEntry, Payment
from tests.test_phase4_social import user
from tests.test_phase5_events_shop import book_event, future, gold_package, order, organizer_with_vendor, shop_with_product

pytestmark = pytest.mark.usefixtures("db")


async def intent(c: AsyncClient, purpose: str, ref: str, key: str | None = None, **extra: object) -> dict:  # type: ignore[type-arg]
    r = await c.post(
        "/api/v1/payments/intents",
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
        json={"purpose": purpose, "reference_id": ref, **extra},
    )
    return {"status_code": r.status_code, **r.json()}


async def test_amount_comes_from_server_and_client_amount_is_rejected(client: AsyncClient) -> None:
    _owner, biz, product = await shop_with_product(client, stock=5)
    buyer = await user(client, "priya")
    oid = (await order(buyer, biz, product, qty=2)).json()["id"]
    r = await intent(buyer, "order", oid, amount_paise=1)
    assert r["status_code"] == 422  # extra="forbid": the client cannot send an amount
    i = await intent(buyer, "order", oid)
    assert i["status_code"] == 201 and i["amount_paise"] == 110000 and i["checkout_url"] == f"/pay/{i['payment_id']}"
    assert (await intent(buyer, "order", oid))["payment_id"] == i["payment_id"]  # reuse open intent
    stranger = await user(client, "stranger")
    assert (await intent(stranger, "order", oid))["status_code"] == 404


async def test_only_signed_webhook_marks_paid_once_with_ledger(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    owner, biz, product = await shop_with_product(client, stock=5)
    buyer = await user(client, "priya")
    oid = (await order(buyer, biz, product, qty=2)).json()["id"]
    i = await intent(buyer, "order", oid)
    async with db() as s:
        p = await s.get(Payment, uuid.UUID(i["payment_id"]))
        provider_order_id = p.provider_order_id

    body, sig, event_id = SandboxProvider.signed_event("evt_1", provider_order_id, "pay_1", 110000)
    forged = await client.post(
        "/api/v1/payments/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": "bad", "X-Razorpay-Event-Id": event_id},
    )
    assert forged.status_code == 401  # and no CSRF token was needed: webhooks are signature-authenticated
    ok = await client.post(
        "/api/v1/payments/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": event_id}
    )
    dup = await client.post(
        "/api/v1/payments/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": event_id}
    )
    assert ok.json() == {"status": "processed"} and dup.json() == {"status": "duplicate"}

    assert [o["payment_status"] for o in (await buyer.get("/api/v1/orders/mine")).json()] == ["paid"]
    async with db() as s:
        entries = sorted((e.entry, e.account, e.amount_paise) for e in (await s.scalars(select(LedgerEntry))).all())
    assert entries == [("charge", "business", 110000), ("platform_fee", "business", -2200), ("platform_fee", "platform", 2200)]
    summary = (await owner.get(f"/api/v1/businesses/{biz['id']}/payouts")).json()
    assert summary["gross_paise"] == 110000 and summary["fees_paise"] == 2200 and summary["due_paise"] == 107800
    assert (await intent(buyer, "order", oid))["status_code"] in (201, 409)  # already paid -> not payable
    with pytest.raises(DBAPIError, match="append-only"):
        async with db() as s:
            await s.execute(text("UPDATE payments.ledger SET amount_paise = 0"))


async def test_amount_mismatch_never_marks_paid(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    _owner, biz, product = await shop_with_product(client)
    buyer = await user(client, "priya")
    oid = (await order(buyer, biz, product)).json()["id"]
    i = await intent(buyer, "order", oid)
    async with db() as s:
        poid = (await s.get(Payment, uuid.UUID(i["payment_id"]))).provider_order_id
    body, sig, eid = SandboxProvider.signed_event("evt_x", poid, "pay_x", 1)
    await client.post(
        "/api/v1/payments/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": eid}
    )
    assert (await buyer.get("/api/v1/orders/mine")).json()[0]["payment_status"] == "unpaid"


async def test_reconciliation_recovers_a_lost_webhook(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    _owner, biz, product = await shop_with_product(client)
    buyer = await user(client, "priya")
    oid = (await order(buyer, biz, product)).json()["id"]
    i = await intent(buyer, "order", oid)
    async with db() as s:
        p = await s.get(Payment, uuid.UUID(i["payment_id"]))
        SandboxProvider.paid[p.provider_order_id] = "pay_lost"  # provider says paid, webhook never arrived
    async with db() as s:
        assert await payments.reconcile(s, older_than=timedelta(0)) == 1
    async with db() as s:
        assert await payments.reconcile(s, older_than=timedelta(0)) == 0
    assert (await buyer.get("/api/v1/orders/mine")).json()[0]["payment_status"] == "paid"


async def test_refund_by_owner_only(client: AsyncClient) -> None:
    owner, biz, product = await shop_with_product(client)
    buyer = await user(client, "priya")
    oid = (await order(buyer, biz, product)).json()["id"]
    i = await intent(buyer, "order", oid)
    assert (await buyer.post(f"/api/v1/payments/{i['payment_id']}/sandbox-complete")).json() == {"status": "processed"}
    assert (await buyer.post(f"/api/v1/payments/{i['payment_id']}/refund", json={})).status_code == 403
    r = await owner.post(f"/api/v1/payments/{i['payment_id']}/refund", json={"amount_paise": 20000})
    assert r.json()["status"] == "partially_refunded" and r.json()["refunded_paise"] == 20000
    assert (await owner.post(f"/api/v1/payments/{i['payment_id']}/refund", json={"amount_paise": 999999})).status_code == 400
    assert (await owner.post(f"/api/v1/payments/{i['payment_id']}/refund", json={})).json()["status"] == "refunded"
    assert (await owner.get(f"/api/v1/businesses/{biz['id']}/payouts")).json()["refunds_paise"] == 55000


async def test_advance_payment_locks_event_date(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    from app.modules.events import service as events

    org, org_biz, _, _ = await organizer_with_vendor(client)
    pkg = await gold_package(org, org_biz)
    fam = await user(client, "family_a")
    eb = (await book_event(fam, pkg, future(40))).json()
    i = await intent(fam, "event_booking", eb["id"])
    assert i["amount_paise"] == 25_000_000 * 20 // 100  # 20 % advance
    await fam.post(f"/api/v1/payments/{i['payment_id']}/sandbox-complete")
    async with db() as s:
        assert await events.expire_holds(s, now=datetime.now(UTC) + timedelta(days=5)) == 0  # paid holds never expire
    mine = (await fam.get("/api/v1/event-bookings/mine")).json()[0]
    assert mine["payment_status"] == "paid" and mine["expires_at"] is None


async def test_subscription_sets_entitlements(client: AsyncClient) -> None:
    u = await user(client, "creator1")
    assert (await u.get("/api/v1/me/entitlements")).json()["plan"] == "free"
    codes = [p["code"] for p in (await client.get("/api/v1/plans")).json()]
    assert codes == ["free", "premium", "creator", "business"]
    assert (await intent(u, "subscription", "free"))["status_code"] == 404  # free plan is not purchasable
    i = await intent(u, "subscription", "business")
    assert i["amount_paise"] == 39900
    await u.post(f"/api/v1/payments/{i['payment_id']}/sandbox-complete")
    ent = (await u.get("/api/v1/me/entitlements")).json()
    assert ent["plan"] == "business" and ent["ai_calls_per_day"] == 500 and ent["renews_at"]
