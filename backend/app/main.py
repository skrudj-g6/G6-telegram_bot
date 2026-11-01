import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import worker
from app.api import (
    admin_auth,
    admin_staff,
    bot_deposits,
    bot_players,
    bot_withdrawals,
    health,
)
from app.api.errors import register_error_handlers
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
    task = asyncio.create_task(worker.run_forever()) if settings.background_jobs_enabled else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Altyn Crown API",
        version="0.5.0",
        lifespan=lifespan,
        # В production документация API не публикуется.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(bot_players.router)
    app.include_router(bot_deposits.router)
    app.include_router(bot_withdrawals.router)
    app.include_router(admin_auth.router)
    app.include_router(admin_staff.router)
    return app


app = create_app()
