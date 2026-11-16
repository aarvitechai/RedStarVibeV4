"""Double-submit CSRF check: every mutating /api/ request needs x-csrf-token equal to the rsv_csrf cookie."""

from collections.abc import Awaitable, Callable

from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.responses import Response

from app.core.cookies import CSRF_COOKIE, CSRF_HEADER
from app.core.errors import error_body
from app.core.security import constant_time_equals

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Server-to-server callers that authenticate by signature instead (added with their modules).
EXEMPT_PREFIXES: tuple[str, ...] = ("/api/v1/payments/webhooks/",)


async def csrf_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    path = request.url.path
    if request.method not in _SAFE_METHODS and path.startswith("/api/") and not path.startswith(EXEMPT_PREFIXES):
        cookie = request.cookies.get(CSRF_COOKIE, "")
        header = request.headers.get(CSRF_HEADER, "")
        if not cookie or not header or not constant_time_equals(cookie, header):
            return JSONResponse(
                error_body("csrf_failed", "Security check failed. Refresh the page and try again."), status_code=403
            )
    return await call_next(request)
