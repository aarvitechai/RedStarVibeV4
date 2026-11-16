"""Import every module's models here so Alembic and the metadata see them."""

from app.core.database import Base
from app.core.events import DeadLetter, OutboxEvent, ProcessedEvent
from app.modules.accounts.models import LoginEvent, Session, User
from app.modules.audit.models import AuditLog

__all__ = ["AuditLog", "Base", "DeadLetter", "LoginEvent", "OutboxEvent", "ProcessedEvent", "Session", "User"]
