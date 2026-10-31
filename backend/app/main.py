import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info(
        "Altyn Crown backend запущен (env=%s, tz=%s)",
        settings.app_env,
        settings.app_timezone,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Altyn Crown API",
        version="0.1.0",
        lifespan=lifespan,
        # В production документация API не публикуется.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.include_router(health.router)
    return app


app = create_app()
