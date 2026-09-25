from unittest.mock import AsyncMock

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


@pytest.mark.asyncio
async def test_local_initialize_does_not_call_telegram(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST_TOKEN_FOR_RUNTIME")
    monkeypatch.setenv(
        "TELEGRAM_BOT_DB_PATH",
        str(tmp_path / "telegram.sqlite3"),
    )
    get_settings.cache_clear()
    runtime = TelegramWebhookRuntime()

    runtime.bot.set_my_commands = AsyncMock(
        side_effect=AssertionError("network call during local init")
    )
    runtime.bot.set_chat_menu_button = AsyncMock(
        side_effect=AssertionError("network call during local init")
    )

    try:
        await runtime.initialize()
        assert runtime._initialized is True
        runtime.bot.set_my_commands.assert_not_awaited()
        runtime.bot.set_chat_menu_button.assert_not_awaited()
    finally:
        await runtime.close()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_optional_telegram_ui_failure_does_not_break_webhook(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST_TOKEN_FOR_RUNTIME")
    monkeypatch.setenv("TELEGRAM_BOT_MODE", "webhook")
    monkeypatch.setenv(
        "TELEGRAM_WEBHOOK_BASE_URL",
        "https://example.pythonanywhere.com",
    )
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test_secret_123")
    monkeypatch.setenv(
        "TELEGRAM_BOT_DB_PATH",
        str(tmp_path / "telegram.sqlite3"),
    )
    get_settings.cache_clear()
    runtime = TelegramWebhookRuntime()

    runtime.bot.set_webhook = AsyncMock(return_value=True)
    runtime.bot.set_my_commands = AsyncMock(side_effect=RuntimeError("commands"))
    runtime.bot.set_chat_menu_button = AsyncMock(side_effect=RuntimeError("menu"))

    try:
        await runtime.configure_webhook()

        assert runtime.state.configured is True
        assert runtime.state.commands_configured is False
        assert runtime.state.menu_configured is False
        runtime.bot.set_webhook.assert_awaited_once()
    finally:
        await runtime.close()
        get_settings.cache_clear()
