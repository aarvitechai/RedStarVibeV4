"""Import every module's event consumers so the dispatcher knows them."""

from app.modules.accounts import consumers as accounts_consumers  # noqa: F401
from app.modules.notifications import consumers as notifications_consumers  # noqa: F401
