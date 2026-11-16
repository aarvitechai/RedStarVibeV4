"""One error shape for every endpoint (ADR 0010):

    {"error": {"code": str, "message": str, "details": dict, "request_id": str}}

Stack traces, SQL and provider internals never reach the client.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id

log = logging.getLogger("rsv.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "The request could not be processed."

    def __init__(self, code: str | None = None, message: str | None = None, details: dict[str, Any] | None = None) -> None:
        self.code = code or self.code
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.code)


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Not found."


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"
    message = "Please sign in."


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    message = "You do not have permission to do this."


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "This conflicts with the current state."


class RateLimited(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests. Please try again later."


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}, "request_id": get_request_id()}}


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
        return JSONResponse(error_body("validation_error", "Some fields are invalid.", {"fields": fields}), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) and exc.status_code < 500 else "Request failed."
        return JSONResponse(error_body(code, message), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", extra={"request_id": get_request_id()})
        return JSONResponse(error_body("internal_error", "Something went wrong. Please try again."), status_code=500)
