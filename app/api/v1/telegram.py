from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.bot.runtime import get_webhook_runtime
from app.config import get_settings

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])


@router.get("/status")
async def telegram_status() -> dict[str, Any]:
    settings = get_settings()
    payload: dict[str, Any] = {
        "mode": settings.TELEGRAM_BOT_MODE,
        "configured": bool(settings.TELEGRAM_BOT_TOKEN),
        "webhook_base_url_configured": bool(settings.TELEGRAM_WEBHOOK_BASE_URL),
        "webhook_secret_configured": bool(settings.TELEGRAM_WEBHOOK_SECRET),
        "webhook_path": settings.TELEGRAM_WEBHOOK_PATH,
        "auto_setup": settings.TELEGRAM_WEBHOOK_AUTO_SETUP,
    }

    if (
        settings.TELEGRAM_BOT_MODE.lower() == "webhook"
        and settings.TELEGRAM_BOT_TOKEN
    ):
        try:
            runtime = await get_webhook_runtime()
            payload["dispatcher_initialized"] = runtime._initialized
            payload["local_webhook_configured"] = runtime.state.configured
            payload["commands_configured"] = runtime.state.commands_configured
            payload["menu_configured"] = runtime.state.menu_configured
            payload["last_setup_error"] = runtime.state.last_error
            payload["commands_error"] = runtime.state.commands_error
            payload["menu_error"] = runtime.state.menu_error
            payload["mini_app_url"] = settings.telegram_mini_app_url
            payload["updates_processed"] = runtime.state.updates_processed
            payload["updates_failed"] = runtime.state.updates_failed
            payload["last_update_id"] = runtime.state.last_update_id
            payload["last_update_at"] = runtime.state.last_update_at
            payload["last_update_error"] = runtime.state.last_update_error
            remote = await runtime.remote_status()
            payload["telegram"] = remote
        except Exception as exc:
            payload["telegram_error"] = str(exc)

    return payload


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(
        default=None,
        alias="X-Telegram-Bot-Api-Secret-Token",
    ),
) -> dict[str, bool]:
    settings = get_settings()

    if settings.TELEGRAM_BOT_MODE.lower() != "webhook":
        raise HTTPException(status_code=404, detail="Webhook mode is disabled.")

    expected_secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected_secret:
        raise HTTPException(
            status_code=503,
            detail="Telegram webhook secret is not configured.",
        )

    if (
        not x_telegram_bot_api_secret_token
        or not secrets.compare_digest(
            x_telegram_bot_api_secret_token,
            expected_secret,
        )
    ):
        raise HTTPException(status_code=403, detail="Invalid Telegram secret.")

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Telegram update.")

    runtime = await get_webhook_runtime()
    handled = await runtime.process_update(payload)
    return {"ok": True, "handled": handled}
