"""App factory for the api process (gunicorn + uvicorn workers run app.main:app)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.asgi import CsrfMiddleware, MetricsMiddleware, RequestIdMiddleware
from app.core.cache import close_redis
from app.core.config import get_settings
from app.core.database import dispose_engine
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.metrics import render
from app.mcp.server import mcp_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await dispose_engine()
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.env != "local")
    app = FastAPI(
        title="RedStarVibe API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.env == "production" else "/api/docs",
        openapi_url=None if settings.env == "production" else "/api/openapi.json",
    )
    # Pure ASGI middleware; the last added runs first: request id -> metrics -> CSRF -> app.
    app.add_middleware(CsrfMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(health_router)
    app.add_api_route("/metrics", render, include_in_schema=False)  # internal port only; not routed by nginx
    app.include_router(api_router)
    app.include_router(mcp_router)  # /mcp (Bearer token, no cookies -> outside CSRF)
    return app


app = create_app()
