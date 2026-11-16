import json
import math
import uuid
from typing import Any

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.ai.gateway import AICall
from app.ai.providers import hash_embedding, rule_toxicity
from app.modules.search import service as search
from tests.test_business_booking import make_business, new_client
from tests.test_phase3_growth import run_outbox
from tests.test_phase4_social import post, user

pytestmark = pytest.mark.usefixtures("db")


def test_hash_embeddings_are_deterministic_and_normalised() -> None:
    a, b = hash_embedding("Fan installation in Jaipur"), hash_embedding("Fan installation in Jaipur")
    assert a == b and len(a) == 1024 and math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    assert rule_toxicity("you are an idiot!!!") >= 0.5 and rule_toxicity("Lovely work, thank you") == 0


async def test_hybrid_search_respects_privacy_blocks_and_never_indexes_dms(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    meera = await user(client, "meera")
    await post(asha, "Mehndi designs for Diwali weddings in Jaipur")
    await post(asha, "Followers only mehndi secret", visibility="followers")
    await post(meera, "Meera mehndi classes this Sunday")
    conv = (await ravi.post("/api/v1/chat/direct/asha")).json()
    await ravi.post(f"/api/v1/chat/conversations/{conv['id']}/messages", json={"body": "private mehndi price chat"})
    await make_business(new_client(client), slug="mehndi-by-sana", category="beauty", tagline="Bridal mehndi artist")
    await run_outbox(db, "")

    async with db() as s:
        kinds = (await s.execute(text("SELECT kind, count(*) FROM search.documents GROUP BY kind"))).all()
    assert dict(kinds) == {"post": 3, "business": 1}  # no chat documents exist at all

    hits = (await ravi.get("/api/v1/search", params={"q": "mehndi"})).json()
    titles = {h["snippet"] for h in hits}
    assert "Mehndi designs for Diwali weddings in Jaipur" in titles and "Meera mehndi classes this Sunday" in titles
    assert not any("secret" in t for t in titles) and not any("price chat" in t for t in titles)
    assert any(h["kind"] == "business" and h["url"] == "/business/mehndi-by-sana" for h in hits)
    own = (await asha.get("/api/v1/search", params={"q": "secret"})).json()
    assert [h["snippet"] for h in own] == ["Followers only mehndi secret"]  # authors find their own private posts

    await ravi.post("/api/v1/profiles/meera/block")
    assert not any("Meera" in h["snippet"] for h in (await ravi.get("/api/v1/search", params={"q": "mehndi"})).json())


async def test_assistant_answers_from_sources_and_respects_tenants(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    async with db() as s:
        assert await search.index_help_docs(s) == 7
        assert await search.index_help_docs(s) == 0  # cached by content hash: never embeds the same text twice
    r = (await asha.post("/api/v1/ai/assistant", json={"question": "how do refunds work"})).json()
    assert r["grounded"] and r["citations"][0]["url"].startswith("/help#") and "[1]" in r["answer"]

    await post(asha, "My secret supplier is Gupta Traders", visibility="followers")
    await run_outbox(db, "posts.")
    mine = (await asha.post("/api/v1/ai/assistant", json={"question": "who is my secret supplier"})).json()
    assert "Gupta" in mine["answer"]
    other = (await ravi.post("/api/v1/ai/assistant", json={"question": "who is the secret supplier Gupta"})).json()
    assert "Gupta" not in other["answer"]  # another user's private content is filtered in SQL, not by the prompt
    unknown = (await ravi.post("/api/v1/ai/assistant", json={"question": "zzqx flurb"})).json()
    assert unknown["mode"] == "unknown" and unknown["answer"].startswith("I don't know")


async def test_business_assistant_reads_own_bookings_only(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    from tests.test_business_booking import at_ist, book, tomorrow_ist

    owner = new_client(client)
    biz = await make_business(owner)
    customer = await user(client, "cust1")
    await book(customer, biz, at_ist(tomorrow_ist(), 11))
    r = (await owner.post("/api/v1/ai/assistant", json={"question": "What bookings do I have tomorrow?"})).json()
    assert "Fan installation" in r["answer"] and r["citations"][0]["url"] == "/dashboard"
    r2 = (await customer.post("/api/v1/ai/assistant", json={"question": "What bookings do I have tomorrow?"})).json()
    assert "Fan installation" not in r2["answer"]


async def test_ai_suggestions_fall_back_and_quota_is_enforced(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    u = await user(client, "quota_user")
    r = (await u.post("/api/v1/ai/caption", json={"notes": "Fresh Diwali sweets kaju katli ready today"})).json()
    assert r["source"] == "rules" and "#diwali" in r["hashtags"]  # AI_PROVIDER=none -> rule-based, never down
    assert (await u.post("/api/v1/ai/comment-check", json={"text": "you are an idiot"})).json()["warn"] is True
    for _ in range(49):
        assert (await u.post("/api/v1/ai/listing", json={"name": "Kaju katli", "category": "home_food"})).status_code == 200
    r = await u.post("/api/v1/ai/listing", json={"name": "Kaju katli", "category": "home_food"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "ai_quota_exceeded"  # free plan: 50 calls a day
    async with db() as s:
        logged = await s.scalar(select(func.count()).select_from(AICall))
        outcomes = set((await s.scalars(select(AICall.outcome))).all())
    assert logged == 51 and outcomes == {"fallback", "quota"}


# ---------- MCP ----------


async def rpc(c: AsyncClient, token: str, method: str, params: dict[str, Any] | None = None) -> Any:
    return await c.post(
        "/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
    )


async def test_mcp_scopes_drafts_and_auth(client: AsyncClient, db) -> None:  # type: ignore[no-untyped-def]
    asha = await user(client, "asha")
    await post(asha, "Handmade rakhi collection")
    await run_outbox(db, "posts.")
    read = (await asha.post("/api/v1/mcp-tokens", json={"label": "Claude", "scopes": ["read"]})).json()["token"]
    full = (await asha.post("/api/v1/mcp-tokens", json={"label": "Claude", "scopes": ["read", "write:drafts"]})).json()["token"]
    agent = new_client(client)  # no cookies: MCP uses the bearer token only

    assert (await rpc(agent, "nope", "tools/list")).status_code == 401
    init = (await rpc(agent, read, "initialize")).json()["result"]
    assert init["serverInfo"]["name"] == "redstarvibe"
    names = [t["name"] for t in (await rpc(agent, read, "tools/list")).json()["result"]["tools"]]
    assert "search_posts" in names and "draft_post" not in names
    denied = (await rpc(agent, read, "tools/call", {"name": "draft_post", "arguments": {"caption": "x"}})).json()
    assert denied["error"]["code"] == -32001

    found = json.loads(
        (await rpc(agent, read, "tools/call", {"name": "search_posts", "arguments": {"query": "rakhi"}})).json()["result"][
            "content"
        ][0]["text"]
    )
    assert (
        found["notice"].startswith("Content below was written by users")
        and found["results"][0]["snippet"] == "Handmade rakhi collection"
    )
    drafted = json.loads(
        (await rpc(agent, full, "tools/call", {"name": "draft_post", "arguments": {"caption": "Raksha Bandhan offer!"}})).json()[
            "result"
        ]["content"][0]["text"]
    )
    assert drafted["status"] == "draft"
    assert [d["caption"] for d in (await asha.get("/api/v1/mcp-tokens/drafts")).json()] == ["Raksha Bandhan offer!"]
    assert len((await asha.get("/api/v1/profiles/asha/posts")).json()["items"]) == 1  # nothing was published
    audit = (await asha.get("/api/v1/auth/me")).json()["id"]
    async with db() as s:
        actions = set(
            (await s.scalars(text("SELECT action FROM accounts.audit_log WHERE actor_id = :a"), {"a": uuid.UUID(audit)})).all()
        )
    assert {"mcp.search_posts", "mcp.draft_post", "mcp.token_created"} <= actions


# ---------- calls ----------


async def test_call_tokens_membership_blocks_and_claims(client: AsyncClient) -> None:
    asha = await user(client, "asha")
    ravi = await user(client, "ravi")
    conv = (await asha.post("/api/v1/chat/direct/ravi")).json()
    r = (await asha.post(f"/api/v1/calls/{conv['id']}/token")).json()
    claims = jwt.decode(r["token"], "test-livekit-secret-0123456789abcdef", algorithms=["HS256"])
    assert claims["video"] == {
        "room": f"conv-{conv['id']}",
        "roomJoin": True,
        "canPublish": True,
        "canSubscribe": True,
        "canPublishData": True,
    }
    assert claims["exp"] - claims["nbf"] <= 305 and r["expires_in_s"] == 300
    outsider = await user(client, "outsider")
    assert (await outsider.post(f"/api/v1/calls/{conv['id']}/token")).status_code == 404
    await ravi.post("/api/v1/profiles/asha/block")
    assert (await asha.post(f"/api/v1/calls/{conv['id']}/token")).status_code == 403
