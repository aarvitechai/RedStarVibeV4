"""Profile the hottest read paths in-process (Phase 8, Level 1). Uses the TEST database, never the app database.

    RSV_TEST_DATABASE_URL=... python -m scripts.profile_hot_paths [requests_per_path]
Prints per-path average wall time, the number of SQL statements per request, and the top functions by own time.
"""

import asyncio
import cProfile
import os
import pstats
import sys
import time
import uuid

os.environ.setdefault("RSV_ENV", "test")
os.environ["RSV_DATABASE_URL"] = os.environ.get(
    "RSV_TEST_DATABASE_URL", "postgresql+asyncpg://rsv:rsvtest@127.0.0.1:55432/rsv_test"
)
os.environ["RSV_REDIS_URL"] = os.environ.get("RSV_TEST_REDIS_URL", "redis://127.0.0.1:56379/15")
os.environ.setdefault("RSV_RATE_LIMIT_SIGNUP_PER_HOUR", "10000")

from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.core.database import get_engine
from app.main import create_app

STATEMENTS = {"n": 0}


async def signup(c: AsyncClient, name: str) -> None:
    c.headers["x-csrf-token"] = (await c.get("/api/v1/auth/csrf")).json()["csrf_token"]
    r = await c.post(
        "/api/v1/auth/signup",
        json={
            "username": name,
            "email": f"{name}@example.com",
            "password": "Prof-Passw0rd-123",
            "display_name": name,
            "is_18_or_older": True,
        },
    )
    assert r.status_code == 201, r.text


async def main(n: int) -> None:
    app = create_app()
    event.listen(
        get_engine().sync_engine, "before_cursor_execute", lambda *a, **k: STATEMENTS.__setitem__("n", STATEMENTS["n"] + 1)
    )
    t = ASGITransport(app=app)
    run = uuid.uuid4().hex[:6]
    owner = AsyncClient(transport=t, base_url="http://p")
    await signup(owner, f"pown{run}")
    biz = (
        await owner.post(
            "/api/v1/businesses", json={"slug": f"prof-{run}", "name": "Profile Electricals", "category": "electrician"}
        )
    ).json()
    await owner.put(
        f"/api/v1/businesses/{biz['id']}/hours", json=[{"weekday": d, "opens": "08:00", "closes": "20:00"} for d in range(7)]
    )
    svc = (
        await owner.post(f"/api/v1/businesses/{biz['id']}/services", json={"name": "Fan", "price_paise": 100, "duration_min": 30})
    ).json()
    for i in range(20):
        await owner.post("/api/v1/posts", json={"caption": f"Fan offer {i} #fans"})
    reader = AsyncClient(transport=t, base_url="http://p")
    await signup(reader, f"prd{run}")
    await reader.post(f"/api/v1/profiles/pown{run}/follow")
    day = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400 * 2))

    paths = {
        "business_page": (reader, f"/api/v1/businesses/by-slug/prof-{run}"),
        "slots": (reader, f"/api/v1/businesses/{biz['id']}/slots?service_id={svc['id']}&date={day}"),
        "feed": (reader, "/api/v1/feed"),
        "search": (reader, "/api/v1/search?q=fan"),
    }
    for name, (client, url) in paths.items():
        await client.get(url)  # warm up
        STATEMENTS["n"] = 0
        prof = cProfile.Profile()
        started, cpu0 = time.perf_counter(), time.process_time()
        prof.enable()
        for _ in range(n):
            r = await client.get(url)
            assert r.status_code == 200, (name, r.status_code, r.text[:200])
        prof.disable()
        took = (time.perf_counter() - started) / n * 1000
        cpu = (time.process_time() - cpu0) / n * 1000
        print(f"\n=== {name}: {took:.1f} ms/request wall, {cpu:.1f} ms CPU (profiled), {STATEMENTS['n'] / n:.1f} SQL/request")
        st = pstats.Stats(prof)
        if os.environ.get("PROFILE_CALLERS"):
            st.sort_stats("tottime").print_callers(os.environ["PROFILE_CALLERS"])
        else:
            st.sort_stats("tottime").print_stats(8)


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 50))
