"""Guards against a task module that exists but is not registered with the worker."""

import importlib
from pathlib import Path

from app.workers.celery_app import TASK_MODULES, celery_app

APP = Path(__file__).resolve().parent.parent / "app"


def test_every_tasks_module_is_registered() -> None:
    on_disk = {f"app.modules.{p.parent.name}.tasks" for p in (APP / "modules").glob("*/tasks.py")}
    assert on_disk <= set(TASK_MODULES), f"add to TASK_MODULES: {sorted(on_disk - set(TASK_MODULES))}"


def test_tasks_register_under_their_names() -> None:
    for module in TASK_MODULES:
        importlib.import_module(module)
    names = set(celery_app.tasks)
    assert {"outbox.relay", "events.dispatch", "media.process", "cards.render", "albums.render_slideshow",
            "booking.send_reminders", "booking.expire_stale"} <= names
