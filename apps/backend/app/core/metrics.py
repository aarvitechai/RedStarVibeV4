"""Prometheus metrics (Blueprint 18): RED per route, DB pool, outbox lag, queue depth, WebSocket connections.

`/metrics` is served on the internal port only; nginx never routes it publicly.
gunicorn runs several workers, so PROMETHEUS_MULTIPROC_DIR must be set (compose does) for correct aggregation.
"""

import os

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest, multiprocess
from starlette.responses import Response

REQUESTS = Counter("rsv_http_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram(
    "rsv_http_request_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5),
)
WS_CONNECTIONS = Gauge("rsv_ws_connections", "Open WebSocket connections", multiprocess_mode="livesum")
OUTBOX_PENDING = Gauge("rsv_outbox_pending", "Unpublished outbox rows", multiprocess_mode="max")
OUTBOX_OLDEST_S = Gauge("rsv_outbox_oldest_seconds", "Age of the oldest unpublished outbox row", multiprocess_mode="max")
DEAD_LETTERS = Gauge("rsv_dead_letters", "Rows in the dead-letter table", multiprocess_mode="max")
QUEUE_DEPTH = Gauge("rsv_queue_depth", "Celery queue length", ["queue"], multiprocess_mode="max")
DB_POOL_CHECKED_OUT = Gauge("rsv_db_pool_checked_out", "DB connections in use (this process)", multiprocess_mode="livesum")


async def _refresh_ops_gauges() -> None:
    """Pull the gauges the worker sampled (see app/workers/ops_tasks.py) and this process's DB pool usage."""
    from app.core.cache import get_redis
    from app.core.database import get_engine

    try:
        data = await get_redis().hgetall("ops:gauges")
    except Exception:
        data = {}
    if data:
        OUTBOX_PENDING.set(float(data.get("outbox_pending", 0)))
        OUTBOX_OLDEST_S.set(float(data.get("outbox_oldest_s", 0)))
        DEAD_LETTERS.set(float(data.get("dead_letters", 0)))
        for q in ("default", "media", "ai"):
            QUEUE_DEPTH.labels(q).set(float(data.get(f"queue_{q}", 0)))
    pool = get_engine().pool
    DB_POOL_CHECKED_OUT.set(float(getattr(pool, "checkedout", lambda: 0)()))


async def render() -> Response:
    await _refresh_ops_gauges()
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
