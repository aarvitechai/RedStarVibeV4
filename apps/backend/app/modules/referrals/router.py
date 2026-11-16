from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.modules.referrals import service
from app.modules.referrals.service import ReferralSummary

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/me", response_model=ReferralSummary)
async def my_referrals(db: DB, user: CurrentUser) -> ReferralSummary:
    return await service.summary(db, user.id)
