"""App factory for the api process (gunicorn + uvicorn workers run app.main:app)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.cache import close_redis
from app.core.config import get_settings
from app.core.csrf import csrf_middleware
from app.core.database import dispose_engine
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.request_context import request_id_middleware


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
    # Starlette runs the last-added middleware first: request id wraps CSRF so rejections carry an id.
    app.middleware("http")(csrf_middleware)
    app.middleware("http")(request_id_middleware)
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
