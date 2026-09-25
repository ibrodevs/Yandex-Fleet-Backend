from __future__ import annotations

import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.bot.runtime import get_webhook_runtime
from app.config import get_settings
from app.core.logging import setup_logging

settings = get_settings()
setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime = None

    if (
        settings.TELEGRAM_BOT_MODE.lower() == "webhook"
        and settings.TELEGRAM_BOT_TOKEN
    ):
        try:
            runtime = await get_webhook_runtime()
            if settings.TELEGRAM_WEBHOOK_AUTO_SETUP:
                await runtime.configure_webhook()
        except Exception:
            logger.exception(
                "Telegram webhook setup failed. "
                "Backend will stay online; check /api/v1/telegram/status."
            )

    yield

    if runtime is not None:
        await runtime.close()


app = FastAPI(
    title="Yandex Fleet Backend",
    version="0.2.0",
    description=(
        "Yandex Fleet integration backend with Telegram park bot "
        "and mock-to-real provider architecture."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

MINIAPP_DIR = Path(__file__).resolve().parent / "miniapp"


@app.get("/miniapp", include_in_schema=False)
async def miniapp_redirect() -> RedirectResponse:
    return RedirectResponse(url="/miniapp/")


app.mount(
    "/miniapp",
    StaticFiles(directory=str(MINIAPP_DIR), html=True),
    name="miniapp",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> dict[str, str | bool]:
    telegram_ready = True

    if settings.TELEGRAM_BOT_MODE.lower() == "webhook":
        telegram_ready = bool(
            settings.TELEGRAM_BOT_TOKEN
            and settings.TELEGRAM_WEBHOOK_BASE_URL
            and settings.TELEGRAM_WEBHOOK_SECRET
        )

    return {
        "status": "ready" if telegram_ready else "degraded",
        "telegram_ready": telegram_ready,
        "mock_mode": settings.YANDEX_MOCK_MODE,
    }


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "yandex-fleet-backend",
        "status": "ok",
        "version": "0.2.0",
    }
