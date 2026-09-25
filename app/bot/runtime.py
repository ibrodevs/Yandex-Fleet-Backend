from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Dispatcher
from aiogram.types import BotCommand, MenuButtonWebApp, Update, WebAppInfo

from app.bot.factory import create_bot
from app.bot.main import build_router
from app.bot.service import LocalBackendService
from app.bot.storage import DriverLinkStore
from app.config import get_settings

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand(command="start", description="Открыть бота"),
    BotCommand(command="profile", description="Профиль водителя"),
    BotCommand(command="orders", description="Заказы"),
    BotCommand(command="stats", description="Статистика"),
    BotCommand(command="app", description="Парковое приложение"),
    BotCommand(command="unlink", description="Управление привязкой"),
]


@dataclass(slots=True)
class WebhookState:
    configured: bool = False
    last_error: str | None = None


class TelegramWebhookRuntime:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.TELEGRAM_BOT_TOKEN:
            raise RuntimeError("TELEGRAM_BOT_TOKEN не задан.")

        self.settings = settings
        self.bot = create_bot(
            settings.TELEGRAM_BOT_TOKEN,
            http_proxy=settings.TELEGRAM_HTTP_PROXY,
        )
        self.dispatcher = Dispatcher()
        self.links = DriverLinkStore(settings.TELEGRAM_BOT_DB_PATH)
        self.backend = LocalBackendService()
        self.state = WebhookState()
        self._initialized = False
        self._init_lock = asyncio.Lock()

    @property
    def webhook_url(self) -> str:
        base = self.settings.TELEGRAM_WEBHOOK_BASE_URL.rstrip("/")
        path = "/" + self.settings.TELEGRAM_WEBHOOK_PATH.strip("/")
        return f"{base}{path}"

    async def initialize(self) -> None:
        if self._initialized:
            return

        async with self._init_lock:
            if self._initialized:
                return

            await self.links.init()
            self.dispatcher.include_router(
                build_router(
                    self.backend,
                    self.links,
                    mock_mode=self.settings.YANDEX_MOCK_MODE,
                    page_size=max(self.settings.TELEGRAM_BOT_ORDERS_PAGE_SIZE, 1),
                    mini_app_url=self.settings.telegram_mini_app_url(),
                )
            )
            await self.bot.set_my_commands(BOT_COMMANDS)
            mini_app_url = self.settings.telegram_mini_app_url()
            if mini_app_url:
                await self.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="🚖 Приложение",
                        web_app=WebAppInfo(url=mini_app_url),
                    )
                )
            self._initialized = True

    async def configure_webhook(self) -> None:
        await self.initialize()

        if not self.settings.TELEGRAM_WEBHOOK_BASE_URL:
            self.state.configured = False
            self.state.last_error = "TELEGRAM_WEBHOOK_BASE_URL не задан."
            raise RuntimeError(self.state.last_error)

        if not self.settings.TELEGRAM_WEBHOOK_SECRET:
            self.state.configured = False
            self.state.last_error = "TELEGRAM_WEBHOOK_SECRET не задан."
            raise RuntimeError(self.state.last_error)

        try:
            await self.bot.set_webhook(
                url=self.webhook_url,
                secret_token=self.settings.TELEGRAM_WEBHOOK_SECRET,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=False,
            )
        except Exception as exc:
            self.state.configured = False
            self.state.last_error = str(exc)
            raise

        self.state.configured = True
        self.state.last_error = None
        logger.info("Telegram webhook configured: %s", self.webhook_url)

    async def process_update(self, payload: dict) -> None:
        await self.initialize()
        update = Update.model_validate(payload, context={"bot": self.bot})
        await self.dispatcher.feed_update(self.bot, update)

    async def remote_status(self) -> dict:
        await self.initialize()
        info = await self.bot.get_webhook_info()
        return {
            "url": info.url,
            "pending_update_count": info.pending_update_count,
            "last_error_message": info.last_error_message,
            "max_connections": info.max_connections,
        }

    async def close(self) -> None:
        await self.bot.session.close()


_runtime: TelegramWebhookRuntime | None = None
_runtime_lock = asyncio.Lock()


async def get_webhook_runtime() -> TelegramWebhookRuntime:
    global _runtime
    if _runtime is not None:
        return _runtime

    async with _runtime_lock:
        if _runtime is None:
            _runtime = TelegramWebhookRuntime()
            await _runtime.initialize()
        return _runtime
