import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from app.api.deps import DB, Client, CurrentUser
from app.modules.payments import service
from app.modules.payments.service import Entitlements, IntentIn, IntentOut, PaymentOut, PayoutSummary, PlanOut

router = APIRouter(tags=["payments"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=80)]


class RefundIn(BaseModel):
    amount_paise: int | None = Field(default=None, gt=0)


@router.post("/payments/intents", response_model=IntentOut, status_code=201)
async def create_intent(body: IntentIn, db: DB, user: CurrentUser, key: IdempotencyKey) -> IntentOut:
    return await service.create_intent(db, user, body, key)


@router.get("/payments/mine", response_model=list[PaymentOut])
async def my_payments(db: DB, user: CurrentUser) -> list[PaymentOut]:
    return await service.my_payments(db, user)


@router.get("/payments/{payment_id}", response_model=IntentOut)
async def get_payment(payment_id: uuid.UUID, db: DB, user: CurrentUser) -> IntentOut:
    return await service.get_mine(db, user, payment_id)


@router.post("/payments/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    db: DB,
    signature: Annotated[str | None, Header(alias="X-Razorpay-Signature")] = None,
    event_id: Annotated[str | None, Header(alias="X-Razorpay-Event-Id")] = None,
) -> dict[str, str]:
    """Signature-authenticated (CSRF-exempt). Acknowledges fast; heavy follow-up runs from outbox events."""
    return {"status": await service.handle_webhook(db, await request.body(), signature, event_id)}


@router.post("/payments/{payment_id}/sandbox-complete")
async def sandbox_complete(payment_id: uuid.UUID, db: DB, user: CurrentUser) -> dict[str, str]:
    """Local/test only (404 when real Razorpay keys are configured)."""
    return {"status": await service.sandbox_complete(db, user, payment_id)}


@router.post("/payments/{payment_id}/refund", response_model=PaymentOut)
async def refund(payment_id: uuid.UUID, body: RefundIn, db: DB, user: CurrentUser, client: Client) -> PaymentOut:
    return await service.refund(db, user, payment_id, body.amount_paise, client.ip)


@router.get("/plans", response_model=list[PlanOut])
async def plans(db: DB) -> list[PlanOut]:
    return await service.plans(db)


@router.get("/me/entitlements", response_model=Entitlements)
async def entitlements(db: DB, user: CurrentUser) -> Entitlements:
    return await service.entitlements(db, user.id)


@router.get("/businesses/{business_id}/payouts", response_model=PayoutSummary)
async def payouts(business_id: uuid.UUID, db: DB, user: CurrentUser) -> PayoutSummary:
    return await service.payout_summary(db, user, business_id)
