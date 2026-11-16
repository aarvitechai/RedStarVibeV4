"""Event consumers owned by accounts. Each is idempotent via the processed_events record."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, consumer
from app.modules.audit import service as audit


@consumer("accounts.user_signed_up", name="accounts.record_signup")
async def record_signup(db: AsyncSession, event: Event) -> None:
    # Placeholder for the welcome notification (notifications module, Phase 2). Records the event for support.
    await audit.record(
        db,
        actor_id=None,
        action="user.signed_up",
        target_type="user",
        target_id=str(event.payload["user_id"]),
        details={"event_id": str(event.event_id)},
    )
