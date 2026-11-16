import io
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.core.events import Event, OutboxEvent, dispatch_event
from app.core.storage import get_storage
from app.modules.cards import service as cards_service
from app.modules.media import service as media_service
from app.modules.media.processing import process_image
from tests.conftest import signup
from tests.test_business_booking import at_ist, book, make_business, new_client, tomorrow_ist

pytestmark = pytest.mark.usefixtures("db")


def jpeg_with_gps(w: int = 1600, h: int = 1200) -> bytes:
    img = Image.new("RGB", (w, h), (200, 30, 40))
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    exif.get_ifd(0x8825)[2] = (26.0, 54.0, 44.0)  # GPSLatitude
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


async def upload_image(client: AsyncClient, db: Any, data: bytes | None = None, purpose: str = "post") -> dict[str, Any]:
    data = data or jpeg_with_gps()
    intent = (
        await client.post(
            "/api/v1/media/uploads",
            json={"kind": "image", "purpose": purpose, "content_type": "image/jpeg", "size_bytes": len(data)},
        )
    ).json()
    storage = get_storage()
    async with db() as s:
        from app.modules.media.models import Asset

        key = (await s.get(Asset, uuid.UUID(intent["asset_id"]))).raw_key
    storage.put_bytes(storage.raw_bucket, key, data, "image/jpeg")  # what the browser's presigned PUT does
    done = (await client.post(f"/api/v1/media/uploads/{intent['asset_id']}/complete")).json()
    assert done["status"] == "processing"
    async with db() as s:
        await media_service.process(s, uuid.UUID(intent["asset_id"]))
    return (await client.get(f"/api/v1/media/{intent['asset_id']}")).json()


async def run_outbox(db: Any, prefix: str) -> None:
    import app.workers.consumers  # noqa: F401

    async with db() as s:
        rows = (await s.scalars(select(OutboxEvent).where(OutboxEvent.type.like(f"{prefix}%")).order_by(OutboxEvent.id))).all()
    for r in rows:
        await dispatch_event(db, Event(r.event_id, r.type, r.version, r.payload, r.created_at))


# ---------- media ----------


def test_process_image_strips_metadata_and_resizes() -> None:
    out = process_image(jpeg_with_gps())
    names = sorted(r.name for r in out.renditions)
    assert names == ["1080.avif", "1080.webp", "320.avif", "320.webp", "640.avif", "640.webp"]
    with Image.open(io.BytesIO(next(r.data for r in out.renditions if r.name == "1080.webp"))) as img:
        assert img.width == 1080 and not img.getexif()


async def test_upload_flow_and_ownership(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    await signup(client, username="uploader")
    asset = await upload_image(client, db)
    assert asset["status"] == "ready" and asset["width"] == 1600
    assert set(asset["urls"]) >= {"640.webp", "1080.avif"}
    storage = get_storage()
    assert not any(b == storage.raw_bucket for b, _ in storage.objects)  # type: ignore[attr-defined]  # raw original deleted
    other = new_client(client)
    await signup(other, username="snooper")
    assert (await other.get(f"/api/v1/media/{asset['id']}")).status_code == 404


async def test_spoofed_and_oversized_uploads_rejected(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    await signup(client, username="uploader")
    r = await client.post("/api/v1/media/uploads", json={"kind": "image", "content_type": "application/pdf", "size_bytes": 10})
    assert r.json()["error"]["code"] == "unsupported_type"
    r = await client.post(
        "/api/v1/media/uploads", json={"kind": "image", "content_type": "image/png", "size_bytes": 50 * 1024 * 1024}
    )
    assert r.json()["error"]["code"] == "file_too_large"
    asset = await upload_image(client, db, data=b"<?php echo 'not an image'; ?>" * 10)
    assert asset["status"] == "failed"


# ---------- cards ----------


async def test_card_create_render_is_idempotent(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    await signup(client, username="cardmaker")
    templates = (await client.get("/api/v1/cards/templates")).json()
    assert {"birthday-en", "diwali-hi"} <= {t["id"] for t in templates}
    photo = await upload_image(client, db, purpose="card")
    r = await client.post(
        "/api/v1/cards",
        json={
            "template_id": "diwali-hi",
            "photo_asset_id": photo["id"],
            "fields": {"title": "शुभ दीपावली", "message": "Happy Diwali to the whole family", "from": "Ravi"},
        },
    )
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["status"] == "rendering"
    async with db() as s:
        assert await cards_service.render(s, uuid.UUID(card["id"])) == "ready"
        assert await cards_service.render(s, uuid.UUID(card["id"])) == "ready"  # retry: no re-render
    public = (await new_client(client).get(f"/api/v1/cards/{card['id']}")).json()
    assert public["status"] == "ready" and public["image_url"].endswith(".png")
    pngs = [k for (_, k) in get_storage().objects if k.startswith("cards/")]  # type: ignore[attr-defined]
    assert len(pngs) == 1
    r = await client.post("/api/v1/cards", json={"template_id": "nope", "fields": {"title": "x"}})
    assert r.status_code == 404


async def test_card_cannot_use_someone_elses_photo(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    await signup(client, username="owner1")
    photo = await upload_image(client, db)
    thief = new_client(client)
    await signup(thief, username="thief1")
    r = await thief.post(
        "/api/v1/cards", json={"template_id": "birthday-en", "photo_asset_id": photo["id"], "fields": {"title": "Hi"}}
    )
    assert r.status_code == 404


async def test_share_image_and_qr(client: AsyncClient) -> None:
    await make_business(client)
    r = await client.get("/api/v1/og/business/sharma-electric.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(r.content)) as img:
        assert img.size == (1200, 630)
    r = await client.get("/api/v1/qr.svg", params={"path": "/business/sharma-electric"})
    assert r.status_code == 200 and "<svg" in r.text
    assert (await client.get("/api/v1/qr.svg", params={"path": "https://evil.example"})).status_code == 400
    assert (await client.get("/api/v1/qr.svg", params={"path": "//evil.example"})).status_code == 400


# ---------- referrals ----------


async def test_referral_qualifies_once_after_first_booking(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    biz = await make_business(client)
    referrer = new_client(client)
    await signup(referrer, username="referrer")
    me = (await referrer.get("/api/v1/referrals/me")).json()
    assert me["link"].endswith(f"/signup?ref={me['code']}") and me["points"] == 0

    friend = new_client(client)
    await signup(friend, username="friend1", referral_code=me["code"])
    await run_outbox(db, "accounts.")
    assert (await referrer.get("/api/v1/referrals/me")).json()["invited"] == 1

    await book(friend, biz, at_ist(tomorrow_ist(), 10))
    await book(friend, biz, at_ist(tomorrow_ist(), 14))
    await run_outbox(db, "booking.")
    await run_outbox(db, "booking.")  # redelivery
    summary = (await referrer.get("/api/v1/referrals/me")).json()
    assert summary["qualified"] == 1 and summary["points"] == 30
    assert (await friend.get("/api/v1/referrals/me")).json()["points"] == 20


async def test_self_referral_is_ignored(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    from app.modules.referrals import service as referrals

    await signup(client, username="selfish")
    me = (await client.get("/api/v1/referrals/me")).json()
    uid = uuid.UUID((await client.get("/api/v1/auth/me")).json()["id"])
    async with db() as s:
        assert await referrals.attribute(s, uid, me["code"]) is False


# ---------- albums ----------


async def test_album_share_and_privacy(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    await signup(client, username="albumowner")
    a1, a2 = await upload_image(client, db), await upload_image(client, db)
    album = (await client.post("/api/v1/albums", json={"title": "Sharma wedding"})).json()
    r = await client.put(f"/api/v1/albums/{album['id']}/items", json={"asset_ids": [a1["id"], a2["id"]]})
    assert r.status_code == 200 and len(r.json()["pages"]) == 2
    token = r.json()["share_token"]
    shared = (await new_client(client).get(f"/api/v1/albums/shared/{token}")).json()
    assert shared["title"] == "Sharma wedding" and len(shared["pages"]) == 2 and shared["share_token"] is None

    stranger = new_client(client)
    await signup(stranger, username="stranger2")
    s_asset = await upload_image(stranger, db)
    assert (await stranger.put(f"/api/v1/albums/{album['id']}/items", json={"asset_ids": [s_asset["id"]]})).status_code == 404
    r = await client.put(f"/api/v1/albums/{album['id']}/items", json={"asset_ids": [s_asset["id"]]})
    assert r.status_code == 404  # cannot add someone else's photo

    private = (await client.post("/api/v1/albums", json={"title": "Private", "visibility": "private"})).json()
    assert (await new_client(client).get(f"/api/v1/albums/shared/{private['share_token']}")).status_code == 404
    r = await client.post(f"/api/v1/albums/{album['id']}/slideshow")
    assert r.status_code == 202 and r.json()["slideshow_status"] == "rendering"
