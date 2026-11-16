"""Reports and the moderation queue. Removal is a human decision, logged in the audit trail (Blueprint 16.3)."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, String, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core import rate_limit
from app.core.database import Base
from app.core.errors import Conflict, NotFound
from app.core.events import emit
from app.core.ids import uuid7
from app.modules.accounts.models import User
from app.modules.audit import service as audit

TargetType = Literal["post", "comment", "profile", "message", "business", "card", "review"]
Reason = Literal["spam", "abuse", "hate", "nudity", "violence", "fraud", "self_harm", "other"]


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = {"schema": "moderation"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    reporter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_type: Mapped[str] = mapped_column(String(12), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolution: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: TargetType
    target_id: uuid.UUID
    reason: Reason
    details: str | None = Field(default=None, max_length=1000)


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    reason: str
    details: str | None
    status: str
    resolution: str | None
    created_at: datetime


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["remove", "dismiss"]


async def create(db: AsyncSession, user: User, data: ReportIn) -> ReportOut:
    await rate_limit.enforce("report_create", str(user.id), limit=30, window_s=3600)
    r = Report(id=uuid7(), reporter_id=user.id, **data.model_dump())
    db.add(r)
    emit(db, "moderation.reported", {"report_id": str(r.id), "target_type": data.target_type, "reason": data.reason})
    await db.commit()
    return ReportOut.model_validate(r)


async def queue(db: AsyncSession, status: str, limit: int) -> list[ReportOut]:
    rows = (await db.scalars(select(Report).where(Report.status == status).order_by(Report.created_at).limit(limit))).all()
    return [ReportOut.model_validate(r) for r in rows]


async def resolve(db: AsyncSession, reviewer: User, report_id: uuid.UUID, data: ResolveIn, ip: str) -> ReportOut:
    r = await db.get(Report, report_id, with_for_update=True)
    if r is None:
        raise NotFound("report_not_found", "Report not found.")
    if r.status != "open":
        raise Conflict("already_resolved", "This report was already handled.")
    if data.action == "remove":
        emit(
            db, "moderation.remove_content", {"target_type": r.target_type, "target_id": str(r.target_id), "report_id": str(r.id)}
        )
    r.status = "actioned" if data.action == "remove" else "dismissed"
    r.resolution, r.reviewer_id, r.resolved_at = data.action, reviewer.id, datetime.now(UTC)
    await audit.record(
        db,
        actor_id=reviewer.id,
        action=f"report.{r.status}",
        target_type=r.target_type,
        target_id=str(r.target_id),
        ip=ip,
        details={"report_id": str(r.id), "reason": r.reason},
    )
    await db.commit()
    return ReportOut.model_validate(r)
