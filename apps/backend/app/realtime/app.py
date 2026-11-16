"""The `ws` process: WebSocket gateway (uvicorn app.realtime.app:app). Typed JSON frames, heartbeat every 25 s.

Auth: the same access cookie as REST. Origin is checked to stop cross-site WebSocket hijacking.
Server -> client frames: hello, ping, message.new, receipt.read, typing. Client -> server: pong.
"""

import asyncio
import contextlib
import json
import logging
from urllib.parse import urlparse

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app.core.cache import close_redis, get_redis
from app.core.config import get_settings
from app.core.cookies import access_cookie_name
from app.core.database import dispose_engine, get_sessionmaker
from app.core.security import TokenExpired, TokenInvalid, decode_access_token
from app.modules.accounts import repository as accounts_repo
from app.realtime.hub import channel

log = logging.getLogger("rsv.ws")
HEARTBEAT_S = 25

app = FastAPI(title="RedStarVibe realtime", docs_url=None, openapi_url=None)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await dispose_engine()
    await close_redis()


def _origin_ok(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if origin is None:
        return False
    expected = urlparse(get_settings().public_base_url)
    got = urlparse(origin)
    return (got.scheme, got.hostname, got.port) == (expected.scheme, expected.hostname, expected.port) or (
        get_settings().env in ("local", "test") and got.hostname in ("localhost", "127.0.0.1")
    )


@app.get("/ws/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def socket(ws: WebSocket) -> None:
    if not _origin_ok(ws):
        await ws.close(code=4403)
        return
    token = ws.cookies.get(access_cookie_name())
    try:
        claims = decode_access_token(token or "")
    except (TokenExpired, TokenInvalid):
        await ws.close(code=4401)  # client refreshes via REST, then reconnects
        return
    async with get_sessionmaker()() as db:
        if not await accounts_repo.family_is_active(db, claims.user_id, claims.session_family):
            await ws.close(code=4401)
            return
    await ws.accept()
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel(claims.user_id))
    await ws.send_json({"type": "hello", "user_id": str(claims.user_id), "heartbeat_s": HEARTBEAT_S})

    async def pump() -> None:
        async for item in pubsub.listen():
            if item.get("type") == "message":
                await ws.send_text(item["data"] if isinstance(item["data"], str) else item["data"].decode())

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            await ws.send_json({"type": "ping"})

    async def receive() -> None:
        while True:
            raw = await ws.receive_text()
            with contextlib.suppress(ValueError):
                if json.loads(raw).get("type") == "pong":
                    continue

    tasks = [asyncio.create_task(t()) for t in (pump, heartbeat, receive)]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    finally:
        for t in tasks:  # never leave background tasks running after a disconnect (Blueprint 27.3)
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(channel(claims.user_id))
            await pubsub.aclose()  # type: ignore[no-untyped-call]
