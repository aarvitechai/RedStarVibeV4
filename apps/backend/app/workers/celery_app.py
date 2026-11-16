"""Celery app for worker and beat processes. Module task files are added to `include` as they are built."""

from celery import Celery
from kombu import Queue  # type: ignore[attr-defined]

from app.core.config import get_settings

settings = get_settings()

# kombu ships without type hints
_queues = tuple(Queue(name) for name in ("default", "media", "ai"))  # type: ignore[no-untyped-call]

# Every module that defines Celery tasks must be listed here (tests/test_workers.py checks this).
TASK_MODULES = [
    "app.workers.outbox_tasks",
    "app.modules.booking.tasks",
    "app.modules.media.tasks",
    "app.modules.cards.tasks",
    "app.modules.albums.tasks",
]

celery_app = Celery("redstarvibe", broker=settings.redis_url, backend=None, include=TASK_MODULES)

celery_app.conf.update(
    task_queues=_queues,
    task_default_queue="default",
    task_acks_late=True,  # tasks are idempotent; redeliver if a worker dies
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=500,  # recycle to contain slow memory leaks (Blueprint 27.3)
    worker_max_memory_per_child=400_000,  # KiB
    task_time_limit=300,
    task_soft_time_limit=240,
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "outbox-relay": {"task": "outbox.relay", "schedule": 2.0, "options": {"expires": 10}},
        "booking-reminders": {"task": "booking.send_reminders", "schedule": 60.0, "options": {"expires": 50}},
        "booking-expiry": {"task": "booking.expire_stale", "schedule": 300.0, "options": {"expires": 250}},
    },
)
