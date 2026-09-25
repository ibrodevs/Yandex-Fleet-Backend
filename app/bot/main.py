from __future__ import annotations

import asyncio
import html
import logging
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.client import BackendClient, BackendError
from app.bot.keyboards import contact_keyboard, main_keyboard, order_keyboard
from app.config import get_settings

logger = logging.getLogger(__name__)


def _money(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return html.escape(str(value))


def _driver_text(driver: dict[str, Any]) -> str:
    name = driver.get("full_name")
    if not name:
        name = " ".join(
            part
            for part in (
                driver.get("first_name"),
                driver.get("last_name"),
            )
            if part
        ).strip()
    rating = driver.get("rating")
    rating_text = "—" if rating is None else str(rating)
    return (
        "<b>Профиль водителя</b>\n\n"
        f"👤 {html.escape(name or '—')}\n"
        f"🆔 <code>{html.escape(str(driver.get('id', '—')))}</code>\n"
        f"📱 {html.escape(str(driver.get('phone') or '—'))}\n"
        f"🚕 {html.escape(str(driver.get('car') or '—'))}\n"
        f"⭐ Рейтинг: {html.escape(rating_text)}\n"
        f"💰 Баланс: {_money(driver.get('balance'))} сом\n"
        f"🟢 Статус: {html.escape(str(driver.get('status') or driver.get('local_driver_state') or '—'))}"
    )


def _order_text(order: dict[str, Any]) -> str:
    return (
        f"<b>Заказ {html.escape(str(order.get('id', '—')))}</b>\n\n"
        f"Статус: <b>{html.escape(str(order.get('status', '—')))}</b>\n"
        f"Откуда: {html.escape(str(order.get('pickup') or order.get('pickup_address') or '—'))}\n"
        f"Куда: {html.escape(str(order.get('destination') or order.get('destination_address') or '—'))}\n"
        f"Цена: {_money(order.get('price'))} {html.escape(str(order.get('currency') or 'KGS'))}"
    )


def build_router(
    backend: BackendClient,
    sessions: dict[int, str],
    mock_mode: bool,
) -> Router:
    router = Router()

    async def require_driver(message: Message) -> str | None:
        if not message.from_user:
            return None
        driver_id = sessions.get(message.from_user.id)
        if driver_id:
            return driver_id
        await message.answer(
            "Сначала нужно войти как водитель.",
            reply_markup=contact_keyboard(),
        )
        return None

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user:
            driver_id = sessions.get(message.from_user.id)
            if driver_id:
                driver = await backend.get_driver(driver_id)
                if driver:
                    await message.answer(
                        f"С возвращением, <b>{html.escape(str(driver.get('full_name') or driver_id))}</b>.",
                        reply_markup=main_keyboard(),
                    )
                    return

        extra = "\n\nДля теста также доступна команда /mocklogin." if mock_mode else ""
        await message.answer(
            "Я парковый бот. Покажу профиль водителя и его заказы.\n\n"
            "Для входа поделитесь номером телефона, привязанным к профилю."
            + extra,
            reply_markup=contact_keyboard(),
        )

    @router.message(Command("mocklogin"))
    async def mock_login(message: Message) -> None:
        if not mock_mode or not message.from_user:
            await message.answer("Mock-вход отключён.")
            return

        driver = await backend.get_driver("driver-001")
        if not driver:
            await message.answer("Тестовый водитель не найден в backend.")
            return

        sessions[message.from_user.id] = str(driver["id"])
        await message.answer(
            "Mock-вход выполнен.",
            reply_markup=main_keyboard(),
        )

    @router.message(F.contact)
    async def contact_login(message: Message) -> None:
        if not message.from_user or not message.contact:
            return

        if (
            message.contact.user_id is not None
            and message.contact.user_id != message.from_user.id
        ):
            await message.answer("Нужно отправить именно свой номер телефона.")
            return

        try:
            driver = await backend.get_driver_by_phone(message.contact.phone_number)
        except BackendError as exc:
            await message.answer(f"Ошибка: {html.escape(str(exc))}")
            return

        if not driver:
            await message.answer(
                "Водитель с таким номером не найден.",
                reply_markup=contact_keyboard(),
            )
            return

        sessions[message.from_user.id] = str(driver["id"])
        await message.answer(
            f"Вход выполнен: <b>{html.escape(str(driver.get('full_name') or driver['id']))}</b>",
            reply_markup=main_keyboard(),
        )

    @router.message(Command("profile"))
    @router.message(F.text == "👤 Профиль")
    async def profile(message: Message) -> None:
        driver_id = await require_driver(message)
        if not driver_id:
            return
        try:
            driver = await backend.get_driver(driver_id)
        except BackendError as exc:
            await message.answer(f"Ошибка: {html.escape(str(exc))}")
            return

        if not driver:
            await message.answer("Профиль водителя не найден.")
            return
        await message.answer(_driver_text(driver), reply_markup=main_keyboard())

    @router.message(Command("orders"))
    @router.message(F.text == "📦 Заказы")
    async def orders(message: Message) -> None:
        driver_id = await require_driver(message)
        if not driver_id:
            return
        try:
            items = await backend.list_orders(driver_id)
        except BackendError as exc:
            await message.answer(f"Ошибка: {html.escape(str(exc))}")
            return

        if not items:
            await message.answer("Заказов пока нет.", reply_markup=main_keyboard())
            return

        await message.answer(f"Найдено заказов: <b>{len(items)}</b>")
        for order in items[:10]:
            await message.answer(
                _order_text(order),
                reply_markup=order_keyboard(order),
            )

    @router.message(F.text == "🔄 Обновить")
    async def refresh(message: Message) -> None:
        driver_id = await require_driver(message)
        if not driver_id:
            return
        try:
            driver = await backend.get_driver(driver_id)
            orders_list = await backend.list_orders(driver_id)
        except BackendError as exc:
            await message.answer(f"Ошибка: {html.escape(str(exc))}")
            return
        if not driver:
            await message.answer("Профиль водителя не найден.")
            return
        await message.answer(
            _driver_text(driver) + f"\n\n📦 Заказов: <b>{len(orders_list)}</b>",
            reply_markup=main_keyboard(),
        )

    @router.message(F.text == "🚪 Выйти")
    async def logout(message: Message) -> None:
        if message.from_user:
            sessions.pop(message.from_user.id, None)
        await message.answer(
            "Вы вышли из профиля.",
            reply_markup=contact_keyboard(),
        )

    @router.callback_query(F.data.startswith("order:"))
    async def refresh_order(query: CallbackQuery) -> None:
        if not query.data:
            return
        order_id = query.data.split(":", 1)[1]
        try:
            order = await backend.get_order(order_id)
        except BackendError as exc:
            await query.answer(str(exc), show_alert=True)
            return

        if not order:
            await query.answer("Заказ не найден.", show_alert=True)
            return
        if query.message:
            try:
                await query.message.edit_text(
                    _order_text(order),
                    reply_markup=order_keyboard(order),
                )
            except TelegramBadRequest as exc:
                if "message is not modified" in str(exc).lower():
                    await query.answer("Без изменений")
                    return
                raise
        await query.answer()

    @router.callback_query(F.data.startswith("complete:"))
    async def complete_order(query: CallbackQuery) -> None:
        if not query.data:
            return
        order_id = query.data.split(":", 1)[1]
        try:
            order = await backend.complete_order(order_id)
        except BackendError as exc:
            await query.answer(str(exc), show_alert=True)
            return

        if query.message:
            await query.message.edit_text(
                _order_text(order) + "\n\n✅ Заказ завершён в mock-режиме.",
                reply_markup=order_keyboard(order),
            )
        await query.answer("Готово")

    return router


async def run() -> None:
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN не задан. Добавьте токен в .env."
        )

    backend = BackendClient(
        settings.TELEGRAM_BOT_BACKEND_URL,
        settings.TELEGRAM_BOT_REQUEST_TIMEOUT_SECONDS,
    )
    sessions: dict[int, str] = {}

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_router(
            backend,
            sessions,
            mock_mode=settings.YANDEX_MOCK_MODE,
        )
    )

    logger.info(
        "Telegram bot starting; backend=%s mock=%s",
        settings.TELEGRAM_BOT_BACKEND_URL,
        settings.YANDEX_MOCK_MODE,
    )

    try:
        await dispatcher.start_polling(bot)
    finally:
        await backend.close()
        await bot.session.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run())


if __name__ == "__main__":
    main()
