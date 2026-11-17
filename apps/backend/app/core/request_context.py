"""Per-request correlation id, available to logs and error responses."""

from contextvars import ContextVar

REQUEST_ID_HEADER = "x-request-id"
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id.get()


def safe_incoming_id(value: str | None) -> str | None:
    # Accept a caller-supplied id only if it is short and plain, so it cannot pollute logs.
    if value and len(value) <= 64 and value.replace("-", "").isalnum():
        return value
    return None
