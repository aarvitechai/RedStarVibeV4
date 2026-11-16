"""Mounts every module router under /api/v1. New modules are included here."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

api_router = APIRouter(prefix="/api/v1")


class MetaResponse(BaseModel):
    name: str
    env: str
    version: str
    ai_provider: str


@api_router.get("/meta", response_model=MetaResponse, tags=["meta"])
async def meta() -> MetaResponse:
    s = get_settings()
    return MetaResponse(name=s.app_name, env=s.env, version="0.1.0", ai_provider=s.ai_provider)


# Module routers are included below as they are built, e.g.:
# from app.modules.accounts.router import router as accounts_router
# api_router.include_router(accounts_router)
