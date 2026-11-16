"""Append-only audit trail for admin, staff and security-relevant actions. Written in the caller's transaction."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: str
    ip: str | None
    details: dict[str, Any]
    created_at: datetime

    @field_validator("ip", mode="before")
    @classmethod
    def _ip(cls, v: object) -> str | None:
        return None if v is None else str(v)


async def record(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: str,
    ip: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(actor_id=actor_id, action=action, target_type=target_type, target_id=target_id, ip=ip, details=details or {}))


async def list_entries(db: AsyncSession, *, before_id: int | None, limit: int) -> list[AuditEntryOut]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if before_id is not None:
        stmt = stmt.where(AuditLog.id < before_id)
    rows = await db.scalars(stmt)
    return [AuditEntryOut.model_validate(r) for r in rows]
