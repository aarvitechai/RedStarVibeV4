import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DB, Client, CurrentUser, require_permission
from app.modules.accounts.models import User
from app.modules.moderation import service
from app.modules.moderation.service import ReportIn, ReportOut, ResolveIn

router = APIRouter(tags=["moderation"])


@router.post("/reports", response_model=ReportOut, status_code=201)
async def report(body: ReportIn, db: DB, user: CurrentUser) -> ReportOut:
    return await service.create(db, user, body)


@router.get("/admin/reports", response_model=list[ReportOut])
async def report_queue(
    db: DB,
    _: Annotated[User, Depends(require_permission("report:review"))],
    status: Annotated[str, Query(pattern="^(open|actioned|dismissed)$")] = "open",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[ReportOut]:
    return await service.queue(db, status, limit)


@router.post("/admin/reports/{report_id}/resolve", response_model=ReportOut)
async def resolve(
    report_id: uuid.UUID,
    body: ResolveIn,
    db: DB,
    client: Client,
    reviewer: Annotated[User, Depends(require_permission("report:review"))],
) -> ReportOut:
    return await service.resolve(db, reviewer, report_id, body, client.ip)
