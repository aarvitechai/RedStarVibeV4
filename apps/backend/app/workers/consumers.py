"""Import every module's event consumers so the dispatcher knows them."""

from app.modules.accounts import consumers as accounts_consumers  # noqa: F401
from app.modules.albums import tasks as albums_tasks  # noqa: F401
from app.modules.cards import consumers as cards_consumers  # noqa: F401
from app.modules.media import consumers as media_consumers  # noqa: F401
from app.modules.notifications import consumers as notifications_consumers  # noqa: F401
from app.modules.referrals import consumers as referrals_consumers  # noqa: F401
