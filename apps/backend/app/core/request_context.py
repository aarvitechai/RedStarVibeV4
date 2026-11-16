"""Per-request correlation id, available to logs and error responses."""

import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "x-request-id"
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id.get()


def _safe_incoming_id(value: str | None) -> str | None:
    # Accept a caller-supplied id only if it is short and plain, so it cannot pollute logs.
    if value and len(value) <= 64 and value.replace("-", "").isalnum():
        return value
    return None


async def request_id_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    request_id = _safe_incoming_id(request.headers.get(REQUEST_ID_HEADER)) or uuid.uuid4().hex
    token = _request_id.set(request_id)
    try:
        response = await call_next(request)
    finally:
        _request_id.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
