"""Import every module's models here so Alembic and the metadata see them."""

from app.core.database import Base
from app.core.events import DeadLetter, OutboxEvent, ProcessedEvent
from app.modules.accounts.models import LoginEvent, Session, User
from app.modules.audit.models import AuditLog
from app.modules.booking.models import Booking, BookingStatusHistory
from app.modules.business.models import Business, BusinessHours, Resource, Service
from app.modules.notifications.models import Notification
from app.modules.reviews.models import Review

__all__ = [
    "AuditLog",
    "Base",
    "Booking",
    "BookingStatusHistory",
    "Business",
    "BusinessHours",
    "DeadLetter",
    "LoginEvent",
    "Notification",
    "OutboxEvent",
    "ProcessedEvent",
    "Resource",
    "Review",
    "Service",
    "Session",
    "User",
]
