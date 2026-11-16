import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.modules.events import service as events_service
from tests.conftest import signup
from tests.test_business_booking import make_business, new_client
from tests.test_phase4_social import user

pytestmark = pytest.mark.usefixtures("db")


def future(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


async def shop_with_product(
    client: AsyncClient, stock: int = 3, slug: str = "ghar-ki-bakery"
) -> tuple[AsyncClient, dict[str, Any], dict[str, Any]]:
    owner = new_client(client)
    biz = await make_business(owner, slug=slug, category="bakery")
    r = await owner.post(
        f"/api/v1/businesses/{biz['id']}/products",
        json={"name": "Eggless chocolate cake", "price_paise": 55000, "stock": stock, "sku": "CAKE-1"},
    )
    assert r.status_code == 201, r.text
    return owner, biz, r.json()


async def order(
    c: AsyncClient, biz: dict[str, Any], product: dict[str, Any], qty: int = 1, key: str | None = None, **extra: Any
) -> Any:
    return await c.post(
        "/api/v1/orders",
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
        json={"business_id": biz["id"], "items": [{"product_id": product["id"], "qty": qty}], **extra},
    )


# ---------- shop ----------


async def test_concurrent_orders_never_oversell(client: AsyncClient) -> None:
    owner, biz, product = await shop_with_product(client, stock=3)
    buyers = [await user(client, f"buyer{i}") for i in range(8)]
    results = await asyncio.gather(*(order(b, biz, product) for b in buyers))
    codes = sorted(r.status_code for r in results)
    assert codes.count(201) == 3 and codes.count(409) == 5, [r.text for r in results]
    assert all(r.json()["error"]["code"] == "out_of_stock" for r in results if r.status_code == 409)
    catalog = (await owner.get(f"/api/v1/businesses/{biz['id']}/products")).json()
    assert catalog[0]["stock"] == 0 and catalog[0]["in_stock"] is False


async def test_order_total_idempotency_and_cancel_restores_stock(client: AsyncClient) -> None:
    owner, biz, product = await shop_with_product(client, stock=5)
    buyer = await user(client, "priya")
    r = await order(
        buyer,
        biz,
        product,
        qty=2,
        key="order-key-1",
        fulfilment="delivery",
        address="12 MI Road, Jaipur",
        wanted_on=future(10),
        note="Write Happy Birthday Riya",
    )
    assert r.status_code == 201 and r.json()["total_paise"] == 110000
    assert (await order(buyer, biz, product, qty=2, key="order-key-1")).status_code == 200  # replay
    assert (await owner.get(f"/api/v1/businesses/{biz['id']}/products")).json()[0]["stock"] == 3

    oid = r.json()["id"]
    seller_view = (await owner.get(f"/api/v1/businesses/{biz['id']}/orders")).json()
    assert seller_view[0]["address"] == "12 MI Road, Jaipur" and seller_view[0]["wanted_on"] == future(10)
    assert (await buyer.post(f"/api/v1/orders/{oid}/status", json={"status": "delivered"})).status_code == 409
    assert (await buyer.post(f"/api/v1/orders/{oid}/status", json={"status": "cancelled"})).json()["status"] == "cancelled"
    assert (await owner.get(f"/api/v1/businesses/{biz['id']}/products")).json()[0]["stock"] == 5


async def test_seller_status_flow_and_permissions(client: AsyncClient) -> None:
    owner, biz, product = await shop_with_product(client)
    buyer = await user(client, "priya")
    oid = (await order(buyer, biz, product)).json()["id"]
    for status in ("confirmed", "ready", "delivered"):
        assert (await owner.post(f"/api/v1/orders/{oid}/status", json={"status": status})).json()["status"] == status
    assert (await buyer.post(f"/api/v1/orders/{oid}/status", json={"status": "cancelled"})).status_code == 409
    stranger = await user(client, "stranger")
    assert (await stranger.post(f"/api/v1/orders/{oid}/status", json={"status": "cancelled"})).status_code == 404
    assert (await stranger.get(f"/api/v1/businesses/{biz['id']}/orders")).status_code == 403
    assert (await order(owner, biz, product)).status_code == 403  # own shop
    r = await order(buyer, biz, product, fulfilment="delivery")
    assert r.json()["error"]["code"] == "address_required"


# ---------- events ----------


async def organizer_with_vendor(
    client: AsyncClient, org_slug: str = "royal-lawn", vendor_client: AsyncClient | None = None, vendor_slug: str = "dj-sonu"
) -> tuple[AsyncClient, dict[str, Any], AsyncClient, dict[str, Any]]:
    org = new_client(client)
    org_biz = await make_business(org, slug=org_slug, category="event")
    if vendor_client is None:
        vendor_client = new_client(client)
        vendor_biz = await make_business(vendor_client, slug=vendor_slug, category="event")
    else:
        vendor_biz = (await vendor_client.get("/api/v1/businesses/mine")).json()[0]
    assert (await org.post(f"/api/v1/businesses/{org_biz['id']}/vendors", json={"vendor_slug": vendor_slug})).status_code == 201
    r = await vendor_client.post(f"/api/v1/businesses/{vendor_biz['id']}/vendor-invites/{org_slug}/accept")
    assert r.json()["status"] == "accepted"
    return org, org_biz, vendor_client, vendor_biz


async def gold_package(org: AsyncClient, org_biz: dict[str, Any], vendor_slug: str = "dj-sonu") -> dict[str, Any]:
    r = await org.post(
        f"/api/v1/businesses/{org_biz['id']}/packages",
        json={
            "name": "Gold wedding",
            "tier": "gold",
            "price_paise": 25_000_000,
            "max_guests": 400,
            "items": [{"label": "Lawn + decoration"}, {"label": "DJ night", "vendor_slug": vendor_slug}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def book_event(c: AsyncClient, pkg: dict[str, Any], day: str, key: str | None = None, guests: int = 250) -> Any:
    return await c.post(
        "/api/v1/event-bookings",
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
        json={"package_id": pkg["id"], "event_date": day, "guests": guests},
    )


async def test_package_requires_accepted_vendor(client: AsyncClient) -> None:
    org = new_client(client)
    org_biz = await make_business(org, slug="royal-lawn", category="event")
    await make_business(new_client(client), slug="dj-sonu", category="event")
    r = await org.post(
        f"/api/v1/businesses/{org_biz['id']}/packages",
        json={"name": "Gold", "price_paise": 100, "max_guests": 10, "items": [{"label": "DJ", "vendor_slug": "dj-sonu"}]},
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "vendor_not_accepted"


async def test_gold_package_blocks_all_vendors_across_organizers(client: AsyncClient) -> None:
    org, org_biz, vendor, vendor_biz = await organizer_with_vendor(client)
    pkg = await gold_package(org, org_biz)
    assert [i["vendor"] for i in pkg["items"]] == [None, "Sharma Electricals"]  # make_business names every business the same

    # A second organizer uses the same DJ.
    org2, org2_biz, _, _ = await organizer_with_vendor(client, org_slug="city-banquet", vendor_client=vendor)
    pkg2 = await gold_package(org2, org2_biz)

    a, b = await user(client, "family_a"), await user(client, "family_b")
    day = future(60)
    assert (await book_event(a, pkg, day)).status_code == 201
    r = await book_event(b, pkg2, day)  # different venue, same DJ, same evening
    assert r.status_code == 409 and r.json()["error"]["code"] == "date_unavailable"
    assert (await book_event(b, pkg2, future(61))).status_code == 201

    cal = (await vendor.get(f"/api/v1/businesses/{vendor_biz['id']}/calendar", params={"start": future(59), "days": 5})).json()
    assert len(cal) == 2 and all(h["as_vendor"] for h in cal)  # vendor sees only its own holds


async def test_event_booking_rules_idempotency_and_release(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    org, org_biz, _, _ = await organizer_with_vendor(client)
    pkg = await gold_package(org, org_biz)
    fam = await user(client, "family_a")
    assert (await book_event(fam, pkg, future(5), guests=999)).json()["error"]["code"] == "too_many_guests"
    assert (await book_event(fam, pkg, date.today().isoformat())).json()["error"]["code"] == "invalid_date"
    first = await book_event(fam, pkg, future(20), key="event-key-1")
    again = await book_event(fam, pkg, future(20), key="event-key-1")
    assert first.status_code == 201 and again.status_code == 200 and first.json()["id"] == again.json()["id"]

    # Unpaid holds expire and free the date.
    async with db() as s:
        assert await events_service.expire_holds(s, now=datetime.now(UTC) + timedelta(hours=49)) == 1
    other = await user(client, "family_b")
    assert (await book_event(other, pkg, future(20))).status_code == 201

    # Cancelling a confirmed booking releases holds too.
    eb = (await book_event(fam, pkg, future(30))).json()
    assert (await org.post(f"/api/v1/event-bookings/{eb['id']}/status", json={"status": "confirmed"})).json()[
        "status"
    ] == "confirmed"
    assert (await fam.post(f"/api/v1/event-bookings/{eb['id']}/status", json={"status": "cancelled"})).json()[
        "status"
    ] == "cancelled"
    assert (await book_event(other, pkg, future(30))).status_code == 201
    assert (await signup(new_client(client), username="late_user")).status_code == 201
