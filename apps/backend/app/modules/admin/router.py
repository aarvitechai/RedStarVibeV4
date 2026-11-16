import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import DB, Client, require_permission
from app.modules.accounts import service as accounts
from app.modules.accounts.models import User
from app.modules.accounts.schemas import UserOut
from app.modules.audit import service as audit
from app.modules.audit.service import AuditEntryOut

router = APIRouter(prefix="/admin", tags=["admin"])


class AuditPage(BaseModel):
    items: list[AuditEntryOut]
    next_cursor: str | None


class RoleChange(BaseModel):
    role: str


@router.get("/audit-log", response_model=AuditPage)
async def audit_log(
    db: DB,
    _: Annotated[User, Depends(require_permission("audit:read"))],
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> AuditPage:
    items = await audit.list_entries(db, before_id=cursor, limit=limit)
    return AuditPage(items=items, next_cursor=str(items[-1].id) if len(items) == limit else None)


@router.patch("/users/{user_id}/role", response_model=UserOut)
async def change_role(
    user_id: uuid.UUID,
    body: RoleChange,
    db: DB,
    client: Client,
    actor: Annotated[User, Depends(require_permission("user:role"))],
) -> UserOut:
    return UserOut.model_validate(await accounts.change_role(db, actor, user_id, body.role, client.ip))
