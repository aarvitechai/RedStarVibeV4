import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.cache import get_redis
from app.realtime.hub import channel
from tests.conftest import signup
from tests.test_business_booking import new_client
from tests.test_phase3_growth import run_outbox, upload_image

pytestmark = pytest.mark.usefixtures("db")


async def user(client: AsyncClient, name: str) -> AsyncClient:
    c = new_client(client)
    r = await signup(c, username=name)
    assert r.status_code == 201, r.text
    return c


async def post(c: AsyncClient, caption: str, **extra: Any) -> dict[str, Any]:
    r = await c.post("/api/v1/posts", json={"caption": caption, **extra})
    assert r.status_code == 201, r.text
    return r.json()


# ---------- follows, privacy, blocks ----------


async def test_private_account_requires_approved_follow(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    await asha.patch("/api/v1/profiles/me", json={"is_private": True, "bio": "Mehndi artist"})
    p = await post(asha, "Private work #mehndi")
    assert (await ravi.get(f"/api/v1/posts/{p['id']}")).status_code == 404
    assert (await ravi.get("/api/v1/profiles/asha/posts")).json()["items"] == []

    assert (await ravi.post("/api/v1/profiles/asha/follow")).json() == {"status": "pending"}
    assert [u["username"] for u in (await asha.get("/api/v1/follow-requests")).json()] == ["ravi"]
    assert (await asha.post("/api/v1/follow-requests/ravi/approve")).status_code == 200
    prof = (await ravi.get("/api/v1/profiles/asha")).json()
    assert prof["relationship"] == "following" and prof["can_view_content"] and prof["followers"] == 1
    assert (await ravi.get(f"/api/v1/posts/{p['id']}")).status_code == 200


async def test_block_hides_everything_both_ways(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    await ravi.post("/api/v1/profiles/asha/follow")
    p = await post(asha, "Hello world")
    await ravi.post(f"/api/v1/posts/{p['id']}/comments", json={"body": "nice"})
    conv = (await ravi.post("/api/v1/chat/direct/asha")).json()

    assert (await asha.post("/api/v1/profiles/ravi/block")).status_code == 200
    # Ravi (blocked) can no longer see Asha anywhere.
    assert (await ravi.get("/api/v1/profiles/asha")).status_code == 404
    assert (await ravi.get(f"/api/v1/posts/{p['id']}")).status_code == 404
    assert (await ravi.post("/api/v1/profiles/asha/follow")).status_code == 404
    assert (await ravi.post("/api/v1/chat/direct/asha")).status_code == 404
    r = await ravi.post(f"/api/v1/chat/conversations/{conv['id']}/messages", json={"body": "hi?"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "blocked"
    assert "asha" not in [u["username"] for u in (await ravi.get("/api/v1/search/users", params={"q": "ash"})).json()]
    # And Asha no longer sees Ravi's comment; the follow was removed.
    assert (await asha.get(f"/api/v1/posts/{p['id']}/comments")).json() == []
    assert (await asha.get("/api/v1/profiles/asha")).json()["followers"] == 0


# ---------- posts ----------


async def test_post_with_photo_like_comment_save(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    photo = await upload_image(asha, db)
    p = await post(asha, "Diwali decor #Diwali #jaipur with @ravi", media_ids=[photo["id"]])
    assert len(p["media"]) == 1 and p["media"][0]["urls"]["640.webp"]

    assert (await ravi.post(f"/api/v1/posts/{p['id']}/like")).json() == {"like_count": 1}
    assert (await ravi.post(f"/api/v1/posts/{p['id']}/like")).json() == {"like_count": 1}  # idempotent
    c1 = (await ravi.post(f"/api/v1/posts/{p['id']}/comments", json={"body": "Beautiful!"})).json()
    reply = (await asha.post(f"/api/v1/posts/{p['id']}/comments", json={"body": "Thanks", "parent_id": c1["id"]})).json()
    assert reply["parent_id"] == c1["id"]
    await ravi.post(f"/api/v1/posts/{p['id']}/save")
    assert [x["id"] for x in (await ravi.get("/api/v1/posts/saved")).json()] == [p["id"]]

    viewed = (await ravi.get(f"/api/v1/posts/{p['id']}")).json()
    assert viewed["liked"] and viewed["saved"] and viewed["comment_count"] == 2
    assert [x["id"] for x in (await new_client(client).get("/api/v1/hashtags/diwali")).json()["items"]] == [p["id"]]

    await run_outbox(db, "posts.")
    titles = [n["title"] for n in (await asha.get("/api/v1/notifications")).json()["items"]]
    assert "Ravi liked your post" in titles and "Ravi commented on your post" in titles
    assert any("mentioned you" in n["title"] for n in (await ravi.get("/api/v1/notifications")).json()["items"])

    # Someone else's photo cannot be attached.
    r = await ravi.post("/api/v1/posts", json={"caption": "stolen", "media_ids": [photo["id"]]})
    assert r.status_code == 404


async def test_feed_fan_out_unfollow_and_delete(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    meera = await user(client, "meera")
    await ravi.post("/api/v1/profiles/asha/follow")
    p1 = await post(asha, "first")
    p2 = await post(asha, "second")
    await post(meera, "not followed")
    await run_outbox(db, "posts.")
    assert await get_redis().zcard(f"feed:{(await ravi.get('/api/v1/auth/me')).json()['id']}") == 2
    feed = (await ravi.get("/api/v1/feed")).json()
    assert [x["id"] for x in feed["items"]] == [p2["id"], p1["id"]]

    await asha.delete(f"/api/v1/posts/{p2['id']}")
    await run_outbox(db, "posts.")
    assert [x["id"] for x in (await ravi.get("/api/v1/feed")).json()["items"]] == [p1["id"]]
    await ravi.delete("/api/v1/profiles/asha/follow")
    assert (await ravi.get("/api/v1/feed")).json()["items"] == []  # read path re-checks the follow


async def test_feed_rebuilds_from_database_when_cache_is_empty(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    await ravi.post("/api/v1/profiles/asha/follow")
    p = await post(asha, "no fan-out ran")
    assert [x["id"] for x in (await ravi.get("/api/v1/feed")).json()["items"]] == [p["id"]]


# ---------- stories ----------


async def test_stories_tray_views_and_expiry(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    meera = await user(client, "meera")
    await ravi.post("/api/v1/profiles/asha/follow")
    photo = await upload_image(asha, db, purpose="story")
    story = (await asha.post("/api/v1/stories", json={"asset_id": photo["id"]})).json()
    tray = (await ravi.get("/api/v1/stories/tray")).json()
    assert [g["username"] for g in tray] == ["asha"] and not tray[0]["all_seen"]
    assert (await meera.get("/api/v1/stories/tray")).json() == []
    await ravi.post(f"/api/v1/stories/{story['id']}/view")
    assert (await ravi.get("/api/v1/stories/tray")).json()[0]["all_seen"]
    assert [v["username"] for v in (await asha.get(f"/api/v1/stories/{story['id']}/viewers")).json()] == ["ravi"]
    assert (await ravi.get(f"/api/v1/stories/{story['id']}/viewers")).status_code == 404
    hl = (await asha.post("/api/v1/highlights", json={"title": "Work", "story_ids": [story["id"]]})).json()
    async with db() as s:
        await s.execute(text("UPDATE stories.stories SET expires_at = :t"), {"t": datetime.now(UTC) - timedelta(minutes=1)})
        await s.commit()
    assert (await ravi.get("/api/v1/stories/tray")).json() == []
    assert [h["id"] for h in (await ravi.get("/api/v1/profiles/asha/highlights")).json()] == [hl["id"]]  # highlights keep it


# ---------- chat ----------


async def test_direct_messages_seq_catch_up_and_dedupe(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    ravi_id = (await ravi.get("/api/v1/auth/me")).json()["id"]
    conv = (await asha.post("/api/v1/chat/direct/ravi")).json()
    assert (await ravi.post("/api/v1/chat/direct/asha")).json()["id"] == conv["id"]  # same conversation

    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel(ravi_id))
    await pubsub.get_message(timeout=1)  # subscribe ack

    seqs = []
    for i in range(3):
        m = (
            await asha.post(f"/api/v1/chat/conversations/{conv['id']}/messages", json={"body": f"msg {i}", "client_id": f"c{i}"})
        ).json()
        seqs.append(m["seq"])
    assert seqs == [1, 2, 3]
    dup = (await asha.post(f"/api/v1/chat/conversations/{conv['id']}/messages", json={"body": "msg 2", "client_id": "c2"})).json()
    assert dup["seq"] == 3  # retry with the same client id is not stored twice

    frame = None
    for _ in range(10):
        msg = await pubsub.get_message(timeout=1)
        if msg and msg["type"] == "message":
            frame = json.loads(msg["data"])
            break
    await pubsub.aclose()
    assert frame and frame["type"] == "message.new" and frame["message"]["seq"] == 1

    # Reconnect catch-up: everything after the last seq the client saw.
    after = (await ravi.get(f"/api/v1/chat/conversations/{conv['id']}/messages", params={"after_seq": 1})).json()
    assert [m["body"] for m in after] == ["msg 1", "msg 2"]
    assert (await ravi.get("/api/v1/chat/conversations")).json()[0]["unread"] == 3
    await ravi.post(f"/api/v1/chat/conversations/{conv['id']}/read", json={"seq": 3})
    assert (await ravi.get("/api/v1/chat/conversations")).json()[0]["unread"] == 0

    outsider = await user(client, "outsider")
    assert (await outsider.get(f"/api/v1/chat/conversations/{conv['id']}/messages")).status_code == 404


async def test_concurrent_sends_get_unique_ordered_seqs(client: AsyncClient) -> None:
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    conv = (await asha.post("/api/v1/chat/direct/ravi")).json()
    url = f"/api/v1/chat/conversations/{conv['id']}/messages"
    results = await asyncio.gather(*(c.post(url, json={"body": f"x{i}"}) for i, c in enumerate([asha, ravi] * 4)))
    assert sorted(r.json()["seq"] for r in results) == list(range(1, 9))


async def test_group_chat_owner_controls(client: AsyncClient) -> None:
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    await user(client, "meera")
    g = (await asha.post("/api/v1/chat/groups", json={"title": "Wedding vendors", "usernames": ["ravi", "meera"]})).json()
    assert len(g["members"]) == 3
    assert (await ravi.delete(f"/api/v1/chat/conversations/{g['id']}/members/meera")).status_code == 403
    assert (await asha.delete(f"/api/v1/chat/conversations/{g['id']}/members/meera")).status_code == 200
    assert len((await asha.get("/api/v1/chat/conversations")).json()[0]["members"]) == 2


# ---------- moderation ----------


async def test_report_and_moderator_removal(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    p = await post(asha, "spammy spam")
    r = await ravi.post("/api/v1/reports", json={"target_type": "post", "target_id": p["id"], "reason": "spam"})
    assert r.status_code == 201
    assert (await ravi.get("/api/v1/admin/reports")).status_code == 403
    mod = await user(client, "moderator1")
    async with db() as s:
        await s.execute(text("UPDATE accounts.users SET role='staff' WHERE username='moderator1'"))
        await s.commit()
    from tests.conftest import enable_mfa

    await enable_mfa(mod)
    queue = (await mod.get("/api/v1/admin/reports")).json()
    assert [q["target_id"] for q in queue] == [p["id"]]
    assert (await mod.post(f"/api/v1/admin/reports/{queue[0]['id']}/resolve", json={"action": "remove"})).json()[
        "status"
    ] == "actioned"
    assert (await mod.post(f"/api/v1/admin/reports/{queue[0]['id']}/resolve", json={"action": "remove"})).status_code == 409
    await run_outbox(db, "moderation.")
    assert (await ravi.get(f"/api/v1/posts/{p['id']}")).status_code == 404
    assert uuid.UUID(p["id"])
