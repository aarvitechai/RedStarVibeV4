import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser
from app.modules.accounts.schemas import OkOut
from app.modules.notifications import service
from app.modules.notifications.service import NotificationPage

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPage)
async def list_notifications(
    db: DB, user: CurrentUser, cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=50)] = 20
) -> NotificationPage:
    return await service.list_for(db, user.id, cursor, limit)


@router.post("/{notification_id}/read", response_model=OkOut)
async def mark_read(notification_id: uuid.UUID, db: DB, user: CurrentUser) -> OkOut:
    await service.mark_read(db, user.id, notification_id)
    return OkOut()
