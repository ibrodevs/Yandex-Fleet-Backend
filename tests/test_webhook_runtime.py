import pytest

from app.bot.runtime import TelegramWebhookRuntime
from app.config import get_settings


@pytest.mark.asyncio
async def test_webhook_runtime_builds_pythonanywhere_url(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST_TOKEN_FOR_RUNTIME")
    monkeypatch.setenv("TELEGRAM_BOT_MODE", "webhook")
    monkeypatch.setenv(
        "TELEGRAM_WEBHOOK_BASE_URL",
        "https://example.pythonanywhere.com",
    )
    monkeypatch.setenv(
        "TELEGRAM_WEBHOOK_SECRET",
        "test_secret_123",
    )
    monkeypatch.setenv(
        "TELEGRAM_HTTP_PROXY",
        "http://proxy.server:3128",
    )

    get_settings.cache_clear()
    runtime = TelegramWebhookRuntime()

    try:
        assert runtime.webhook_url == (
            "https://example.pythonanywhere.com"
            "/api/v1/telegram/webhook"
        )
    finally:
        await runtime.close()
        get_settings.cache_clear()
