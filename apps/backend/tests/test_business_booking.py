import asyncio
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError

from app.core.events import Event, OutboxEvent, dispatch_event
from app.modules.booking import service as booking_service
from app.modules.booking.models import Booking
from app.modules.booking.slots import candidates
from tests.conftest import signup

pytestmark = pytest.mark.usefixtures("db")
IST = ZoneInfo("Asia/Kolkata")


def new_client(c: AsyncClient) -> AsyncClient:
    return AsyncClient(transport=c._transport, base_url="http://test")  # type: ignore[attr-defined]


def tomorrow_ist() -> date:
    return (datetime.now(IST) + timedelta(days=1)).date()


def at_ist(day: date, hh: int, mm: int = 0) -> str:
    return datetime.combine(day, time(hh, mm), tzinfo=IST).isoformat()


async def make_business(owner: AsyncClient, slug: str = "sharma-electric", **extra: Any) -> dict[str, Any]:
    await signup(owner, username=slug.replace("-", "_")[:30])
    body = {
        "slug": slug,
        "name": "Sharma Electricals",
        "category": "electrician",
        "phone": "+91 98765 43210",
        "area": "Civil Lines",
        "city": "Jaipur",
        "lat": 26.9124,
        "lng": 75.7873,
        **extra,
    }
    r = await owner.post("/api/v1/businesses", json=body)
    assert r.status_code == 201, r.text
    biz = r.json()
    r = await owner.put(
        f"/api/v1/businesses/{biz['id']}/hours", json=[{"weekday": d, "opens": "09:00", "closes": "18:00"} for d in range(7)]
    )
    assert r.status_code == 200, r.text
    r = await owner.post(
        f"/api/v1/businesses/{biz['id']}/services",
        json={"name": "Fan installation", "price_paise": 49900, "duration_min": 60, "buffer_min": 30},
    )
    assert r.status_code == 201, r.text
    biz["service"] = r.json()
    return biz


async def book(customer: AsyncClient, biz: dict[str, Any], starts_at: str, key: str | None = None) -> Any:
    return await customer.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": key or uuid.uuid4().hex},
        json={"business_id": biz["id"], "service_id": biz["service"]["id"], "starts_at": starts_at},
    )


# ---------- pure slot arithmetic ----------


def test_candidates_respect_hours_duration_and_lead_time() -> None:
    day = date(2027, 1, 4)  # a Monday
    now = datetime(2027, 1, 4, 9, 40, tzinfo=IST).astimezone(UTC)
    c = candidates(day, IST, [(time(9), time(12))], duration_min=60, buffer_min=15, now=now)
    starts = [x.starts_at.astimezone(IST).strftime("%H:%M") for x in c]
    assert starts == ["10:30", "11:00"]  # 09:00-10:00 too soon (30 min lead); last start fits 60 min before 12:00
    assert c[0].blocks_until - c[0].starts_at == timedelta(minutes=75)


# ---------- business ----------


async def test_create_business_promotes_role_and_encrypts_phone(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    biz = await make_business(client)
    assert biz["phone"] == "+919876543210"
    assert biz["resources"][0]["name"] == "Owner"
    assert (await client.get("/api/v1/auth/me")).json()["role"] == "business"
    async with db() as s:
        raw = await s.scalar(text("SELECT phone_enc FROM business.businesses"))
    assert b"9876543210" not in bytes(raw)


async def test_public_page_hides_private_fields(client: AsyncClient) -> None:
    await make_business(client)
    r = await new_client(client).get("/api/v1/businesses/by-slug/SHARMA-ELECTRIC")
    assert r.status_code == 200
    page = r.json()
    assert page["name"] == "Sharma Electricals" and len(page["services"]) == 1 and len(page["hours"]) == 7
    assert "phone" not in page and "owner_id" not in page


async def test_reserved_and_duplicate_slugs(client: AsyncClient) -> None:
    await make_business(client)
    r = await client.post("/api/v1/businesses", json={"slug": "admin", "name": "X Y", "category": "other"})
    assert r.status_code == 422
    r = await client.post("/api/v1/businesses", json={"slug": "sharma-electric", "name": "X Y", "category": "other"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "slug_taken"


async def test_other_users_cannot_manage_a_business(client: AsyncClient) -> None:
    biz = await make_business(client)
    intruder = new_client(client)
    await signup(intruder, username="intruder")
    await intruder.post("/api/v1/businesses", json={"slug": "intruder-shop", "name": "Intruder", "category": "shop"})
    # Has business:manage permission, but does not own this business -> 404 (not 403, ids are not probed).
    r = await intruder.patch(f"/api/v1/businesses/{biz['id']}", json={"name": "Hacked"})
    assert r.status_code == 404
    r = await intruder.post(
        f"/api/v1/businesses/{biz['id']}/services", json={"name": "Xyz", "price_paise": 1, "duration_min": 10}
    )
    assert r.status_code == 404
    r = await intruder.get(f"/api/v1/businesses/{biz['id']}/bookings", params={"date": str(tomorrow_ist())})
    assert r.status_code == 404


async def test_plain_user_lacks_manage_permission(client: AsyncClient) -> None:
    biz = await make_business(client)
    user = new_client(client)
    await signup(user, username="plainuser")
    r = await user.patch(f"/api/v1/businesses/{biz['id']}", json={"name": "Hacked"})
    assert r.status_code == 403


async def test_nearby_search(client: AsyncClient) -> None:
    await make_business(client)
    other = new_client(client)
    await make_business(other, slug="far-away-bakery", category="bakery", lat=28.6139, lng=77.2090)  # Delhi
    anon = new_client(client)
    r = await anon.get("/api/v1/businesses/nearby", params={"lat": 26.92, "lng": 75.79, "radius_km": 5})
    assert [b["slug"] for b in r.json()] == ["sharma-electric"]
    assert r.json()[0]["distance_km"] < 2
    r = await anon.get("/api/v1/businesses/nearby", params={"lat": 26.92, "lng": 75.79, "radius_km": 5, "category": "bakery"})
    assert r.json() == []


# ---------- booking ----------


async def test_slots_then_booking_removes_slot(client: AsyncClient) -> None:
    biz = await make_business(client)
    customer = new_client(client)
    await signup(customer, username="customer1")
    day = tomorrow_ist()
    slots = (
        await customer.get(f"/api/v1/businesses/{biz['id']}/slots", params={"service_id": biz["service"]["id"], "date": str(day)})
    ).json()["slots"]
    assert len(slots) == 17  # 09:00..17:00 every 30 min
    r = await book(customer, biz, at_ist(day, 10))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending" and r.json()["price_paise"] == 49900
    slots = (
        await customer.get(f"/api/v1/businesses/{biz['id']}/slots", params={"service_id": biz["service"]["id"], "date": str(day)})
    ).json()["slots"]
    starts = {datetime.fromisoformat(s["starts_at"]).astimezone(IST).strftime("%H:%M") for s in slots}
    # Booked 10:00-11:30 (60 min + 30 min buffer). Any slot whose own 90-minute block overlaps is gone:
    # 09:00 (blocks to 10:30) through 11:00. 11:30 is the first free slot after it.
    assert not starts & {"09:00", "09:30", "10:00", "10:30", "11:00"} and "11:30" in starts
    assert len(starts) == 12


async def test_booking_outside_hours_or_owner_booking_rejected(client: AsyncClient) -> None:
    biz = await make_business(client)
    r = await book(client, biz, at_ist(tomorrow_ist(), 10))
    assert r.status_code == 403 and r.json()["error"]["code"] == "own_business"
    customer = new_client(client)
    await signup(customer, username="customer1")
    r = await book(customer, biz, at_ist(tomorrow_ist(), 20))
    assert r.status_code == 400 and r.json()["error"]["code"] == "slot_unavailable"
    r = await customer.post(
        "/api/v1/bookings",
        json={"business_id": biz["id"], "service_id": biz["service"]["id"], "starts_at": at_ist(tomorrow_ist(), 10)},
    )
    assert r.status_code == 422  # Idempotency-Key header is required


async def test_idempotency_key_replay_returns_same_booking(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    biz = await make_business(client)
    customer = new_client(client)
    await signup(customer, username="customer1")
    first = await book(customer, biz, at_ist(tomorrow_ist(), 10), key="retry-key-123")
    again = await book(customer, biz, at_ist(tomorrow_ist(), 10), key="retry-key-123")
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    async with db() as s:
        assert len((await s.scalars(select(Booking))).all()) == 1


async def test_two_customers_race_for_one_slot_exactly_one_wins(client: AsyncClient) -> None:
    biz = await make_business(client)
    a, b = new_client(client), new_client(client)
    await signup(a, username="customer_a")
    await signup(b, username="customer_b")
    results = await asyncio.gather(book(a, biz, at_ist(tomorrow_ist(), 14)), book(b, biz, at_ist(tomorrow_ist(), 14)))
    codes = sorted(r.status_code for r in results)
    assert codes == [201, 409], [r.text for r in results]
    loser = next(r for r in results if r.status_code == 409)
    assert loser.json()["error"]["code"] == "slot_taken"


async def test_second_resource_allows_parallel_booking(client: AsyncClient) -> None:
    biz = await make_business(client)
    await client.post(f"/api/v1/businesses/{biz['id']}/resources", json={"name": "Helper Raju"})
    a, b = new_client(client), new_client(client)
    await signup(a, username="customer_a")
    await signup(b, username="customer_b")
    ra, rb = await book(a, biz, at_ist(tomorrow_ist(), 14)), await book(b, biz, at_ist(tomorrow_ist(), 14))
    assert ra.status_code == rb.status_code == 201
    assert ra.json()["resource_id"] != rb.json()["resource_id"]


async def test_database_constraint_blocks_overlap_even_without_the_service(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    biz = await make_business(client)
    customer = new_client(client)
    await signup(customer, username="customer1")
    first = (await book(customer, biz, at_ist(tomorrow_ist(), 10))).json()
    start = datetime.fromisoformat(first["starts_at"])
    async with db() as s:
        s.add(
            Booking(
                business_id=uuid.UUID(biz["id"]),
                resource_id=uuid.UUID(first["resource_id"]),
                service_id=uuid.UUID(biz["service"]["id"]),
                customer_id=uuid.uuid4(),
                slot=Range(start + timedelta(minutes=15), start + timedelta(minutes=75)),
                starts_at=start + timedelta(minutes=15),
                ends_at=start + timedelta(minutes=75),
                status="confirmed",
                service_name="x",
                price_paise=0,
                idempotency_key="direct-insert",
            )
        )
        with pytest.raises(IntegrityError, match="exclu"):
            await s.commit()


async def test_status_machine_and_permissions(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    biz = await make_business(client)
    customer = new_client(client)
    await signup(customer, username="customer1")
    bk = (await book(customer, biz, at_ist(tomorrow_ist(), 10))).json()

    # Customers cannot confirm; strangers cannot see it.
    assert (await customer.post(f"/api/v1/bookings/{bk['id']}/confirm")).status_code == 403
    stranger = new_client(client)
    await signup(stranger, username="stranger")
    assert (await stranger.post(f"/api/v1/bookings/{bk['id']}/cancel")).status_code == 404

    r = await client.post(f"/api/v1/bookings/{bk['id']}/confirm")
    assert r.status_code == 200 and r.json()["status"] == "confirmed"
    r = await client.post(f"/api/v1/bookings/{bk['id']}/complete")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_started"
    r = await client.post(f"/api/v1/bookings/{bk['id']}/confirm")
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_transition"

    day = await client.get(f"/api/v1/businesses/{biz['id']}/bookings", params={"date": str(tomorrow_ist())})
    assert [b["id"] for b in day.json()] == [bk["id"]]
    mine = await customer.get("/api/v1/bookings/mine")
    assert [b["id"] for b in mine.json()["items"]] == [bk["id"]]

    r = await customer.post(f"/api/v1/bookings/{bk['id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    # The slot is free again.
    other = new_client(client)
    await signup(other, username="customer2")
    assert (await book(other, biz, at_ist(tomorrow_ist(), 10))).status_code == 201


async def _complete(db, owner_id: str, booking_id: str) -> None:  # type: ignore[no-untyped-def]
    from app.modules.accounts.models import User

    async with db() as s:
        owner = await s.get(User, uuid.UUID(owner_id))
        bk = await s.get(Booking, uuid.UUID(booking_id))
        later = bk.starts_at + timedelta(hours=1)
        if bk.status == "pending":
            await booking_service.transition(s, owner, bk.id, "confirmed", now=later)
        await booking_service.transition(s, owner, bk.id, "done", now=later)


async def test_review_only_after_completion_and_owner_reply(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    biz = await make_business(client)
    customer = new_client(client)
    await signup(customer, username="customer1")
    bk = (await book(customer, biz, at_ist(tomorrow_ist(), 10))).json()

    r = await customer.post(f"/api/v1/bookings/{bk['id']}/review", json={"rating": 5, "body": "Great work"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "booking_not_done"

    await _complete(db, biz["owner_id"], bk["id"])
    r = await customer.post(f"/api/v1/bookings/{bk['id']}/review", json={"rating": 5, "body": "Great work"})
    assert r.status_code == 201
    review = r.json()
    assert (await customer.post(f"/api/v1/bookings/{bk['id']}/review", json={"rating": 1})).status_code == 409

    stranger = new_client(client)
    await make_business(stranger, slug="other-biz")
    assert (await stranger.post(f"/api/v1/reviews/{review['id']}/reply", json={"body": "spam"})).status_code == 404
    r = await client.post(f"/api/v1/reviews/{review['id']}/reply", json={"body": "Thank you!"})
    assert r.status_code == 200 and r.json()["reply_body"] == "Thank you!"

    page = (await new_client(client).get(f"/api/v1/businesses/{biz['id']}/reviews")).json()
    assert page["count"] == 1 and page["average"] == 5.0 and page["items"][0]["customer_name"] == "Customer1"


async def test_booking_events_notify_both_sides_once(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    import app.workers.consumers  # noqa: F401

    biz = await make_business(client)
    customer = new_client(client)
    await signup(customer, username="customer1")
    bk = (await book(customer, biz, at_ist(tomorrow_ist(), 10))).json()
    await client.post(f"/api/v1/bookings/{bk['id']}/confirm")

    async with db() as s:
        rows = (await s.scalars(select(OutboxEvent).where(OutboxEvent.type.like("booking.%")).order_by(OutboxEvent.id))).all()
    for row in rows:
        ev = Event(row.event_id, row.type, row.version, row.payload, row.created_at)
        await dispatch_event(db, ev)
        await dispatch_event(db, ev)  # redelivery must not duplicate

    owner_feed = (await client.get("/api/v1/notifications")).json()
    customer_feed = (await customer.get("/api/v1/notifications")).json()
    assert [n["type"] for n in owner_feed["items"]] == ["booking.new"]
    assert sorted(n["type"] for n in customer_feed["items"]) == ["booking.confirmed", "booking.requested"]
    assert customer_feed["unread"] == 2
    nid = customer_feed["items"][0]["id"]
    assert (await client.post(f"/api/v1/notifications/{nid}/read")).status_code == 404  # not the owner's
    assert (await customer.post(f"/api/v1/notifications/{nid}/read")).status_code == 200
    assert (await customer.get("/api/v1/notifications")).json()["unread"] == 1


async def test_reminders_and_expiry_jobs(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    biz = await make_business(client)
    customer = new_client(client)
    await signup(customer, username="customer1")
    confirmed = (await book(customer, biz, at_ist(tomorrow_ist(), 10))).json()
    pending = (await book(customer, biz, at_ist(tomorrow_ist(), 15))).json()
    await client.post(f"/api/v1/bookings/{confirmed['id']}/confirm")

    soon = datetime.fromisoformat(confirmed["starts_at"]) - timedelta(hours=1)
    async with db() as s:
        assert await booking_service.send_reminders(s, now=soon) == 1
    async with db() as s:
        assert await booking_service.send_reminders(s, now=soon) == 0  # never twice
    after = datetime.fromisoformat(pending["starts_at"]) + timedelta(minutes=1)
    async with db() as s:
        assert await booking_service.expire_stale(s, now=after) == 1
        assert (await s.get(Booking, uuid.UUID(pending["id"]))).status == "expired"
