"""Opaque cursors for keyset pagination (never OFFSET on large tables)."""

import base64
import json
from typing import Any

from app.core.errors import AppError


def encode_cursor(values: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(values, default=str).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError("invalid_cursor", "This page link is invalid.") from exc
    if not isinstance(data, dict):
        raise AppError("invalid_cursor", "This page link is invalid.")
    return data
