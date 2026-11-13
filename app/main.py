import logging
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import aiosqlite
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes.webhook import router as webhook_router
from app.config import Settings
from app.logging_config import configure_logging
from app.queue_store import QueueStore

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    queue: QueueStore | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_settings = settings or Settings()
        app_settings.require_webhook_secret()
        configure_logging(app_settings.log_level)
        event_queue = queue or QueueStore(
            app_settings.database_path,
            app_settings.dedup_retention_days,
        )
        await event_queue.initialize()
        app.state.settings = app_settings
        app.state.queue = event_queue
        yield

    application = FastAPI(
        title="GitHub Telegram Monitor",
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(webhook_router)

    @application.get("/")
    async def service_info() -> dict[str, str]:
        return {"service": "GitHub Telegram Monitor", "version": __version__}

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready")
    async def readiness() -> JSONResponse:
        event_queue: QueueStore = application.state.queue
        try:
            await event_queue.check_ready()
        except (aiosqlite.Error, OSError, sqlite3.Error) as exc:
            logger.error(
                "readiness_check_failed",
                extra={"error_type": type(exc).__name__},
            )
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "dependencies": {"sqlite": "unavailable"}},
            )
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "dependencies": {"sqlite": "ok"}},
        )

    return application


app = create_app()
