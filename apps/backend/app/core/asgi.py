"""Pure ASGI middleware (Phase 8, Level 1).

Starlette's BaseHTTPMiddleware (`@app.middleware("http")`) runs every request through an extra task group and
memory streams; three such layers cost measurable CPU per request. These classes do the same work directly on
the ASGI messages.
"""

import time
import uuid
from typing import Any

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.cookies import CSRF_COOKIE, CSRF_HEADER
from app.core.errors import error_body
from app.core.metrics import LATENCY, REQUESTS
from app.core.request_context import REQUEST_ID_HEADER, _request_id, safe_incoming_id
from app.core.security import constant_time_equals

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Server-to-server callers that authenticate by signature instead.
CSRF_EXEMPT_PREFIXES: tuple[str, ...] = ("/api/v1/payments/webhooks/",)


def _header(scope: Scope, name: bytes) -> str | None:
    for k, v in scope.get("headers", []):
        if k == name:
            return str(v.decode("latin-1"))
    return None


def _cookie(scope: Scope, name: str) -> str:
    raw = _header(scope, b"cookie") or ""
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return ""


class RequestIdMiddleware:
    """Correlation id for logs and error bodies; echoed in the x-request-id response header."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = safe_incoming_id(_header(scope, REQUEST_ID_HEADER.encode())) or uuid.uuid4().hex
        token = _request_id.set(rid)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((REQUEST_ID_HEADER.encode(), rid.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _request_id.reset(token)


class CsrfMiddleware:
    """Double-submit CSRF check: every mutating /api/ request needs x-csrf-token equal to the rsv_csrf cookie."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path: str = scope["path"]
            if scope["method"] not in _SAFE_METHODS and path.startswith("/api/") and not path.startswith(CSRF_EXEMPT_PREFIXES):
                cookie = _cookie(scope, CSRF_COOKIE)
                header = _header(scope, CSRF_HEADER.encode()) or ""
                if not cookie or not header or not constant_time_equals(cookie, header):
                    body = error_body("csrf_failed", "Security check failed. Refresh the page and try again.")
                    await JSONResponse(body, status_code=403)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def route_template(scope: Scope) -> str:
    """Full route pattern (/api/v1/posts/{post_id}), never raw ids, so label cardinality stays bounded.
    Reads what the router stored in the (shared) scope after matching."""
    if scope.get("route") is None:
        return "unmatched"
    params = {str(v): k for k, v in (scope.get("path_params") or {}).items()}
    return "/".join(f"{{{params[seg]}}}" if seg in params else seg for seg in scope["path"].split("/"))


class MetricsMiddleware:
    """RED metrics per route template (Blueprint 18)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] == "/metrics":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status: dict[str, Any] = {"code": 500}

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            route = route_template(scope)
            LATENCY.labels(scope["method"], route).observe(time.perf_counter() - started)
            REQUESTS.labels(scope["method"], route, str(status["code"])).inc()
