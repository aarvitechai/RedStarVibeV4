"""Import every module's models here so Alembic and the metadata see them."""

from app.core.database import Base
from app.core.events import DeadLetter, OutboxEvent, ProcessedEvent
from app.modules.accounts.models import LoginEvent, Session, User
from app.modules.albums.models import Album, AlbumItem
from app.modules.audit.models import AuditLog
from app.modules.booking.models import Booking, BookingStatusHistory
from app.modules.business.models import Business, BusinessHours, Resource, Service
from app.modules.cards.models import Card, CardTemplate
from app.modules.chat.service import Conversation, Member, Message
from app.modules.events.service import EventBooking, Hold, Package, PackageItem, VendorLink
from app.modules.media.models import Asset
from app.modules.moderation.service import Report
from app.modules.notifications.models import Notification
from app.modules.payments.service import LedgerEntry, Payment, Plan, Subscription, WebhookEvent
from app.modules.posts.models import Comment, Like, Post, PostHashtag, Save
from app.modules.referrals.models import PointsEntry, Referral, ReferralCode
from app.modules.reviews.models import Review
from app.modules.shop.service import Order, OrderItem, OrderStatusHistory, Product
from app.modules.social.models import Block, Follow, Mute, Profile
from app.modules.stories.service import Highlight, HighlightItem, Story, StoryView

__all__ = [
    "Album",
    "AlbumItem",
    "Asset",
    "AuditLog",
    "Base",
    "Block",
    "Booking",
    "BookingStatusHistory",
    "Business",
    "BusinessHours",
    "Card",
    "CardTemplate",
    "Comment",
    "Conversation",
    "DeadLetter",
    "EventBooking",
    "Follow",
    "Highlight",
    "HighlightItem",
    "Hold",
    "LedgerEntry",
    "Like",
    "LoginEvent",
    "Member",
    "Message",
    "Mute",
    "Notification",
    "Order",
    "OrderItem",
    "OrderStatusHistory",
    "OutboxEvent",
    "Package",
    "PackageItem",
    "Payment",
    "Plan",
    "PointsEntry",
    "Post",
    "PostHashtag",
    "ProcessedEvent",
    "Product",
    "Profile",
    "Referral",
    "ReferralCode",
    "Report",
    "Resource",
    "Review",
    "Save",
    "Service",
    "Session",
    "Story",
    "StoryView",
    "Subscription",
    "User",
    "VendorLink",
    "WebhookEvent",
]
