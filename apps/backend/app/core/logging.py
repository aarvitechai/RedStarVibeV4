"""Structured JSON logs. Every line carries request_id. Never log secrets, tokens, OTPs or full phone numbers."""

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.request_context import get_request_id


def _add_request_id(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    event_dict.setdefault("request_id", get_request_id())
    return event_dict


def configure_logging(level: str = "INFO", json: bool = True) -> None:
    renderer: structlog.types.Processor = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_request_id,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=level.upper(), format="%(message)s")
