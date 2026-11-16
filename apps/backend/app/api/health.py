"""Liveness and readiness. Deploys wait for /health/ready before switching traffic."""

import asyncio
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.database import get_engine

router = APIRouter(prefix="/health", tags=["health"])

CheckStatus = Literal["ok", "fail"]


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: CheckStatus
    checks: dict[str, CheckStatus]


async def _check_db() -> CheckStatus:
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))
    return "ok"


async def _check_redis() -> CheckStatus:
    await get_redis().ping()
    return "ok"


async def _run(check: str) -> CheckStatus:
    probe = _check_db if check == "database" else _check_redis
    try:
        return await asyncio.wait_for(probe(), timeout=get_settings().health_check_timeout_s)
    except Exception:
        return "fail"


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse()


@router.get("/ready", response_model=ReadyResponse, responses={503: {"model": ReadyResponse}})
async def ready() -> JSONResponse:
    names = ("database", "redis")
    results = await asyncio.gather(*(_run(n) for n in names))
    checks: dict[str, CheckStatus] = dict(zip(names, results, strict=True))
    ok = all(v == "ok" for v in checks.values())
    body = ReadyResponse(status="ok" if ok else "fail", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if ok else 503)
