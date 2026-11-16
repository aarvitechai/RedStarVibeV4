"""Payments (Blueprint 9.6, Phase 6).

Rules:
- The amount is always computed on the server from database records; the client never sends an amount.
- Only a verified webhook (or the reconciliation job asking the provider) marks a payment paid. The browser's
  success screen is only a hint.
- Provider event ids are unique, so duplicate webhooks change nothing.
- Every money movement is an append-only ledger row in integer paise.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.errors import AppError, Conflict, Forbidden, NotFound, Unauthorized
from app.core.events import emit
from app.core.ids import uuid7
from app.core.permissions import has_permission
from app.modules.accounts.models import User
from app.modules.payments.providers import PaymentProvider, SandboxProvider, get_provider

log = logging.getLogger("rsv.payments")

ADVANCE_PERCENT = 20  # event package advance that locks the date
COMMISSION_BPS = {"order": 200, "event_booking": 500, "subscription": 0}  # platform fee in basis points
Purpose = Literal["order", "event_booking", "subscription"]


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = {"schema": "payments"}  # noqa: RUF012
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(64), nullable=False)
    business_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    provider: Mapped[str] = mapped_column(String(12), nullable=False)
    provider_order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    provider_payment_id: Mapped[str | None] = mapped_column(String(64))
    refunded_paise: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = {"schema": "payments"}  # noqa: RUF012
    provider_event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    provider: Mapped[str] = mapped_column(String(12), nullable=False)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LedgerEntry(Base):
    __tablename__ = "ledger"
    __table_args__ = {"schema": "payments"}  # noqa: RUF012
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entry: Mapped[str] = mapped_column(String(16), nullable=False)  # charge | platform_fee | refund | payout
    account: Mapped[str] = mapped_column(String(12), nullable=False)  # business | platform
    business_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = {"schema": "payments"}  # noqa: RUF012
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    ai_calls_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    features: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = {"schema": "payments"}  # noqa: RUF012
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    plan_code: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IntentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: Purpose
    reference_id: str = Field(min_length=1, max_length=64, description="Order id, event booking id, or plan code")


class IntentOut(BaseModel):
    payment_id: uuid.UUID
    amount_paise: int
    currency: Literal["INR"] = "INR"
    provider: str
    provider_order_id: str
    public_key: str
    checkout_url: str
    status: str


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    purpose: str
    reference_id: str
    amount_paise: int
    status: str
    provider: str
    refunded_paise: int
    created_at: datetime
    paid_at: datetime | None


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    price_paise: int
    ai_calls_per_day: int
    features: list[str]


class Entitlements(BaseModel):
    plan: str
    ai_calls_per_day: int
    features: list[str]
    renews_at: datetime | None


class PayoutSummary(BaseModel):
    business_id: uuid.UUID
    gross_paise: int
    fees_paise: int
    refunds_paise: int
    paid_out_paise: int
    due_paise: int


def provider() -> PaymentProvider:
    return get_provider()


async def _amount_for(db: AsyncSession, user: User, purpose: str, reference_id: str) -> tuple[int, uuid.UUID | None]:
    """Server-side price lookup. Returns (amount_paise, business receiving the money)."""
    if purpose == "order":
        from app.modules.shop import service as shop

        o = await shop.order_for_payment(db, user.id, _uuid(reference_id))
        return int(o.total_paise), o.business_id
    if purpose == "event_booking":
        from app.modules.events import service as events

        eb = await events.booking_for_payment(db, user.id, _uuid(reference_id))
        return int(eb.price_paise) * ADVANCE_PERCENT // 100, eb.organizer_id
    plan = await db.get(Plan, reference_id)
    if plan is None or not plan.active or plan.price_paise <= 0:
        raise NotFound("plan_not_found", "Plan not found.")
    return int(plan.price_paise), None


def _uuid(v: str) -> uuid.UUID:
    try:
        return uuid.UUID(v)
    except ValueError as exc:
        raise NotFound("reference_not_found", "Not found.") from exc


async def create_intent(db: AsyncSession, user: User, data: IntentIn, idempotency_key: str) -> IntentOut:
    existing = await db.scalar(select(Payment).where(Payment.user_id == user.id, Payment.idempotency_key == idempotency_key))
    if existing is None:
        existing = await db.scalar(
            select(Payment).where(
                Payment.user_id == user.id,
                Payment.purpose == data.purpose,
                Payment.reference_id == data.reference_id,
                Payment.status == "created",
            )
        )
    if existing is not None:
        return _intent_out(existing)
    amount, business_id = await _amount_for(db, user, data.purpose, data.reference_id)
    if amount <= 0:
        raise AppError("nothing_to_pay", "There is nothing to pay.")
    pid = uuid7()
    order = await provider().create_order(amount, receipt=str(pid), notes={"payment_id": str(pid), "purpose": data.purpose})
    p = Payment(
        id=pid,
        user_id=user.id,
        purpose=data.purpose,
        reference_id=data.reference_id,
        business_id=business_id,
        amount_paise=amount,
        provider=provider().name,
        provider_order_id=order.provider_order_id,
        idempotency_key=idempotency_key,
    )
    db.add(p)
    await db.commit()
    return _intent_out(p, order.public_key)


def _intent_out(p: Payment, public_key: str | None = None) -> IntentOut:
    return IntentOut(
        payment_id=p.id,
        amount_paise=p.amount_paise,
        provider=p.provider,
        provider_order_id=p.provider_order_id,
        public_key=public_key or ("sandbox" if p.provider == "sandbox" else ""),
        checkout_url=f"/pay/{p.id}",
        status=p.status,
    )


async def get_mine(db: AsyncSession, user: User, payment_id: uuid.UUID) -> IntentOut:
    p = await db.get(Payment, payment_id)
    if p is None or p.user_id != user.id:
        raise NotFound("payment_not_found", "Payment not found.")
    from app.core.config import get_settings

    return _intent_out(p, get_settings().razorpay_key_id or "sandbox")


async def _apply_paid(db: AsyncSession, p: Payment, provider_payment_id: str) -> bool:
    """Idempotent: a paid payment is never processed twice."""
    if p.status == "paid":
        return False
    p.status, p.provider_payment_id, p.paid_at = "paid", provider_payment_id, datetime.now(UTC)
    fee = p.amount_paise * COMMISSION_BPS.get(p.purpose, 0) // 10_000
    db.add(
        LedgerEntry(
            payment_id=p.id,
            entry="charge",
            account="business" if p.business_id else "platform",
            business_id=p.business_id,
            amount_paise=p.amount_paise,
        )
    )
    if fee and p.business_id:
        db.add(
            LedgerEntry(payment_id=p.id, entry="platform_fee", account="business", business_id=p.business_id, amount_paise=-fee)
        )
        db.add(LedgerEntry(payment_id=p.id, entry="platform_fee", account="platform", business_id=None, amount_paise=fee))
    if p.purpose == "order":
        from app.modules.shop import service as shop

        await shop.mark_paid(db, uuid.UUID(p.reference_id))
    elif p.purpose == "event_booking":
        from app.modules.events import service as events

        await events.mark_advance_paid(db, uuid.UUID(p.reference_id))
    else:
        sub = await db.get(Subscription, p.user_id)
        base = max(datetime.now(UTC), sub.current_period_end) if sub and sub.status == "active" else datetime.now(UTC)
        await db.execute(
            insert(Subscription)
            .values(user_id=p.user_id, plan_code=p.reference_id, status="active", current_period_end=base + timedelta(days=30))
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={"plan_code": p.reference_id, "status": "active", "current_period_end": base + timedelta(days=30)},
            )
        )
    emit(
        db,
        "payments.paid",
        {"payment_id": str(p.id), "user_id": str(p.user_id), "purpose": p.purpose, "amount_paise": p.amount_paise},
    )
    return True


def _redact(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only what we need; never store card/UPI/contact details from the provider (Blueprint 9.3)."""
    ent = payload.get("payload", {}).get("payment", {}).get("entity", {})
    return {"event": payload.get("event"), "payment": {k: ent.get(k) for k in ("id", "order_id", "amount", "status", "currency")}}


async def handle_webhook(db: AsyncSession, body: bytes, signature: str | None, event_id: str | None) -> str:
    prov = provider()
    if not prov.verify_webhook(body, signature):
        raise Unauthorized("invalid_signature", "Invalid webhook signature.")
    payload = json.loads(body)
    event_id = event_id or f"{payload.get('event')}:{payload.get('payload', {}).get('payment', {}).get('entity', {}).get('id')}"
    inserted = await db.scalar(
        insert(WebhookEvent)
        .values(
            provider_event_id=event_id[:80], provider=prov.name, type=str(payload.get("event", ""))[:60], payload=_redact(payload)
        )
        .on_conflict_do_nothing()
        .returning(WebhookEvent.provider_event_id)
    )
    if inserted is None:
        return "duplicate"
    ent = payload.get("payload", {}).get("payment", {}).get("entity", {})
    if payload.get("event") in ("payment.captured", "order.paid") and ent.get("order_id"):
        p = await db.scalar(select(Payment).where(Payment.provider_order_id == ent["order_id"]).with_for_update())
        if p is None:
            log.warning("webhook_for_unknown_order order=%s", ent.get("order_id"))
        elif int(ent.get("amount", -1)) != p.amount_paise:
            log.error("webhook_amount_mismatch payment=%s", p.id)  # never mark paid on a mismatch; reconcile manually
        else:
            await _apply_paid(db, p, str(ent["id"]))
    await db.commit()
    return "processed"


async def sandbox_complete(db: AsyncSession, user: User, payment_id: uuid.UUID) -> str:
    """Local/test only: simulate the provider calling our webhook (same verification and processing path)."""
    prov = provider()
    if not isinstance(prov, SandboxProvider):
        raise NotFound()
    p = await db.get(Payment, payment_id)
    if p is None or p.user_id != user.id:
        raise NotFound("payment_not_found", "Payment not found.")
    pay_id = f"sbx_pay_{payment_id.hex[:12]}"
    SandboxProvider.paid[p.provider_order_id] = pay_id
    body, sig, event_id = SandboxProvider.signed_event(f"evt_{pay_id}", p.provider_order_id, pay_id, p.amount_paise)
    return await handle_webhook(db, body, sig, event_id)


async def reconcile(db: AsyncSession, older_than: timedelta = timedelta(minutes=10)) -> int:
    """Every 15 min: ask the provider about payments still 'created' (covers lost webhooks)."""
    cutoff = datetime.now(UTC) - older_than
    rows = (
        await db.scalars(
            select(Payment)
            .where(Payment.status == "created", Payment.created_at <= cutoff)
            .limit(200)
            .with_for_update(skip_locked=True)
        )
    ).all()
    fixed = 0
    for p in rows:
        try:
            pay_id = await provider().order_paid_payment_id(p.provider_order_id)
        except Exception:
            log.warning("reconcile_provider_error payment=%s", p.id)
            continue
        if pay_id and await _apply_paid(db, p, pay_id):
            fixed += 1
    await db.commit()
    return fixed


async def refund(db: AsyncSession, actor: User, payment_id: uuid.UUID, amount_paise: int | None, ip: str) -> PaymentOut:
    p = await db.get(Payment, payment_id, with_for_update=True)
    if p is None:
        raise NotFound("payment_not_found", "Payment not found.")
    allowed = has_permission(actor.role, "*")
    if not allowed and p.business_id:
        from app.modules.business import service as business

        try:
            await business.owned(db, p.business_id, actor)
            allowed = True
        except NotFound:
            allowed = False
    if not allowed:
        raise Forbidden("cannot_refund", "Only the business or an admin can refund this payment.")
    if p.status not in ("paid", "partially_refunded") or not p.provider_payment_id:
        raise Conflict("not_refundable", "Only paid payments can be refunded.")
    amount = amount_paise or (p.amount_paise - p.refunded_paise)
    if amount <= 0 or amount > p.amount_paise - p.refunded_paise:
        raise AppError("invalid_refund_amount", "Refund amount is more than what was paid.")
    await provider().refund(p.provider_payment_id, amount)
    p.refunded_paise += amount
    p.status = "refunded" if p.refunded_paise == p.amount_paise else "partially_refunded"
    db.add(
        LedgerEntry(
            payment_id=p.id,
            entry="refund",
            account="business" if p.business_id else "platform",
            business_id=p.business_id,
            amount_paise=-amount,
        )
    )
    from app.modules.audit import service as audit

    await audit.record(
        db,
        actor_id=actor.id,
        action="payment.refunded",
        target_type="payment",
        target_id=str(p.id),
        ip=ip,
        details={"amount_paise": amount},
    )
    await db.commit()
    return PaymentOut.model_validate(p)


async def my_payments(db: AsyncSession, user: User) -> list[PaymentOut]:
    rows = (
        await db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(50))
    ).all()
    return [PaymentOut.model_validate(p) for p in rows]


async def plans(db: AsyncSession) -> list[PlanOut]:
    rows = (await db.scalars(select(Plan).where(Plan.active.is_(True)).order_by(Plan.price_paise))).all()
    return [PlanOut.model_validate(p) for p in rows]


async def entitlements(db: AsyncSession, user_id: uuid.UUID) -> Entitlements:
    """Plan limits are enforced in services from this single source (Blueprint 19.5)."""
    sub = await db.get(Subscription, user_id)
    code = sub.plan_code if sub and sub.status == "active" and sub.current_period_end > datetime.now(UTC) else "free"
    plan = await db.get(Plan, code) or await db.get(Plan, "free")
    assert plan is not None
    return Entitlements(
        plan=plan.code,
        ai_calls_per_day=plan.ai_calls_per_day,
        features=list(plan.features),
        renews_at=sub.current_period_end if sub and code != "free" else None,
    )


async def payout_summary(db: AsyncSession, owner: User, business_id: uuid.UUID) -> PayoutSummary:
    from app.modules.business import service as business

    b = await business.owned(db, business_id, owner)
    rows = (
        await db.execute(
            select(LedgerEntry.entry, func.coalesce(func.sum(LedgerEntry.amount_paise), 0))
            .where(LedgerEntry.business_id == b.id, LedgerEntry.account == "business")
            .group_by(LedgerEntry.entry)
        )
    ).all()
    totals = {entry: int(total) for entry, total in rows}
    gross, fees, refunds, paid_out = (
        totals.get("charge", 0),
        -totals.get("platform_fee", 0),
        -totals.get("refund", 0),
        -totals.get("payout", 0),
    )
    return PayoutSummary(
        business_id=b.id,
        gross_paise=gross,
        fees_paise=fees,
        refunds_paise=refunds,
        paid_out_paise=paid_out,
        due_paise=gross - fees - refunds - paid_out,
    )
