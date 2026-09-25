from __future__ import annotations

import asyncio
import html
import logging
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, CallbackQuery, Message

from app.bot.client import BackendClient, BackendError
from app.bot.factory import create_bot
from app.bot.keyboards import (
    binding_keyboard,
    confirm_unlink_keyboard,
    contact_keyboard,
    main_keyboard,
    order_keyboard,
    orders_keyboard,
)
from app.bot.presenters import (
    driver_profile_text,
    order_list_line,
    order_text,
    stats_text,
)
from app.bot.storage import DriverLinkStore
from app.bot.service import BotBackend
from app.config import get_settings

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = {"assigned", "waiting", "in_progress"}


async def _safe_edit(
    message: Any,
    text: str,
    *,
    reply_markup: Any = None,
) -> bool:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise


def build_router(
    backend: BotBackend,
    links: DriverLinkStore,
    *,
    mock_mode: bool,
    page_size: int,
) -> Router:
    router = Router()

    async def linked_driver_id(telegram_user_id: int) -> str | None:
        return await links.get_driver_id(telegram_user_id)

    async def require_driver(message: Message) -> str | None:
        if not message.from_user:
            return None

        driver_id = await linked_driver_id(message.from_user.id)
        if not driver_id:
            await message.answer(
                "Сначала привяжите Telegram к профилю водителя.",
                reply_markup=contact_keyboard(),
            )
            return None

        try:
            driver = await backend.get_driver(driver_id)
        except BackendError as exc:
            await message.answer(
                f"Backend временно недоступен: {html.escape(str(exc))}"
            )
            return None

        if not driver:
            await links.unlink(message.from_user.id)
            await message.answer(
                "Привязанный профиль водителя больше не найден. "
                "Пройдите привязку заново.",
                reply_markup=contact_keyboard(),
            )
            return None

        return driver_id

    async def require_callback_driver(query: CallbackQuery) -> str | None:
        driver_id = await linked_driver_id(query.from_user.id)
        if not driver_id:
            await query.answer(
                "Сначала привяжите профиль водителя.",
                show_alert=True,
            )
            return None
        return driver_id

    async def send_profile(message: Message, driver_id: str) -> None:
        try:
            driver = await backend.get_driver(driver_id)
            summary = await backend.get_driver_summary(driver_id)
        except BackendError as exc:
            await message.answer(f"Ошибка: {html.escape(str(exc))}")
            return

        if not driver:
            await message.answer("Профиль водителя не найден.")
            return

        await message.answer(
            driver_profile_text(driver, summary),
            reply_markup=main_keyboard(),
        )

    async def orders_page_data(
        driver_id: str,
        page: int,
    ) -> tuple[list[dict[str, Any]], int, int]:
        page = max(page, 0)
        items, total = await backend.list_orders(
            driver_id,
            limit=page_size,
            offset=page * page_size,
        )

        if not items and page > 0 and total > 0:
            page = max((total - 1) // page_size, 0)
            items, total = await backend.list_orders(
                driver_id,
                limit=page_size,
                offset=page * page_size,
            )
        return items, total, page

    def orders_page_text(
        items: list[dict[str, Any]],
        *,
        total: int,
        page: int,
    ) -> str:
        if not items:
            return "<b>📦 Заказы</b>\n\nЗаказов пока нет."

        start = page * page_size + 1
        end = start + len(items) - 1
        lines = [
            "<b>📦 Заказы</b>",
            f"Показаны {start}–{end} из {total}",
            "",
        ]
        for index, order in enumerate(items, start=start):
            lines.append(f"<b>{index}.</b> {order_list_line(order)}")
        lines.append("")
        lines.append("Нажмите на заказ ниже, чтобы открыть детали.")
        return "\n".join(lines)

    async def send_orders_page(
        target: Message,
        driver_id: str,
        *,
        page: int = 0,
        edit: bool = False,
    ) -> bool:
        try:
            items, total, page = await orders_page_data(driver_id, page)
        except BackendError as exc:
            if edit:
                return await _safe_edit(
                    target,
                    f"Ошибка backend: {html.escape(str(exc))}",
                )
            await target.answer(f"Ошибка backend: {html.escape(str(exc))}")
            return True

        text = orders_page_text(items, total=total, page=page)
        markup = orders_keyboard(
            items,
            page=page,
            page_size=page_size,
            total=total,
        )

        if edit:
            return await _safe_edit(target, text, reply_markup=markup)

        await target.answer(text, reply_markup=markup)
        return True

    async def get_owned_order(
        query: CallbackQuery,
        driver_id: str,
        order_id: str,
    ) -> dict[str, Any] | None:
        try:
            order = await backend.get_order(order_id)
        except BackendError as exc:
            await query.answer(str(exc), show_alert=True)
            return None

        if not order:
            await query.answer("Заказ не найден.", show_alert=True)
            return None

        if str(order.get("driver_id")) != str(driver_id):
            await query.answer(
                "Этот заказ не принадлежит вашему профилю.",
                show_alert=True,
            )
            return None

        return order

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if not message.from_user:
            return

        driver_id = await linked_driver_id(message.from_user.id)
        if driver_id:
            try:
                driver = await backend.get_driver(driver_id)
            except BackendError:
                driver = None

            if driver:
                await message.answer(
                    "Привязка восстановлена после запуска бота.\n\n"
                    f"Водитель: <b>{html.escape(str(driver.get('full_name') or driver_id))}</b>",
                    reply_markup=main_keyboard(),
                )
                return

            await links.unlink(message.from_user.id)

        extra = (
            "\n\nДля разработки в mock-режиме доступна команда /mocklogin."
            if mock_mode
            else ""
        )
        await message.answer(
            "<b>Парковый бот</b>\n\n"
            "Для привязки нажмите кнопку ниже и отправьте свой номер Telegram. "
            "Номер должен совпадать с номером в профиле водителя."
            + extra,
            reply_markup=contact_keyboard(),
        )

    @router.message(Command("mocklogin"))
    async def mock_login(message: Message) -> None:
        if not mock_mode or not message.from_user:
            await message.answer("Mock-вход отключён.")
            return

        try:
            driver = await backend.get_driver("driver-001")
        except BackendError as exc:
            await message.answer(f"Ошибка backend: {html.escape(str(exc))}")
            return

        if not driver:
            await message.answer("Тестовый водитель не найден.")
            return

        await links.link(
            telegram_user_id=message.from_user.id,
            driver_id=str(driver["id"]),
            phone=driver.get("phone"),
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        await message.answer(
            "✅ Тестовый профиль привязан к вашему Telegram.",
            reply_markup=main_keyboard(),
        )
        await send_profile(message, str(driver["id"]))

    @router.message(F.contact)
    async def contact_login(message: Message) -> None:
        if not message.from_user or not message.contact:
            return

        if message.contact.user_id != message.from_user.id:
            await message.answer(
                "Для безопасности нужно отправить именно свой контакт "
                "кнопкой «Поделиться номером».",
                reply_markup=contact_keyboard(),
            )
            return

        try:
            driver = await backend.get_driver_by_phone(
                message.contact.phone_number
            )
        except BackendError as exc:
            await message.answer(f"Ошибка backend: {html.escape(str(exc))}")
            return

        if not driver:
            await message.answer(
                "В парке не найден водитель с этим номером.",
                reply_markup=contact_keyboard(),
            )
            return

        await links.link(
            telegram_user_id=message.from_user.id,
            driver_id=str(driver["id"]),
            phone=message.contact.phone_number,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )

        await message.answer(
            "✅ Telegram успешно привязан к профилю водителя. "
            "Привязка сохранится после перезапуска бота.",
            reply_markup=main_keyboard(),
        )
        await send_profile(message, str(driver["id"]))

    @router.message(Command("profile"))
    @router.message(F.text == "👤 Профиль")
    async def profile(message: Message) -> None:
        driver_id = await require_driver(message)
        if driver_id:
            await send_profile(message, driver_id)

    @router.message(Command("stats"))
    @router.message(F.text == "📊 Статистика")
    async def stats(message: Message) -> None:
        driver_id = await require_driver(message)
        if not driver_id:
            return
        try:
            summary = await backend.get_driver_summary(driver_id)
        except BackendError as exc:
            await message.answer(f"Ошибка: {html.escape(str(exc))}")
            return
        if not summary:
            await message.answer("Статистика пока недоступна.")
            return
        await message.answer(stats_text(summary), reply_markup=main_keyboard())

    @router.message(Command("orders"))
    @router.message(F.text == "📦 Заказы")
    async def orders(message: Message) -> None:
        driver_id = await require_driver(message)
        if driver_id:
            await send_orders_page(message, driver_id)

    @router.message(F.text == "🚕 Активный заказ")
    async def active_order(message: Message) -> None:
        driver_id = await require_driver(message)
        if not driver_id:
            return

        try:
            items, _ = await backend.list_orders(driver_id, limit=50)
        except BackendError as exc:
            await message.answer(f"Ошибка: {html.escape(str(exc))}")
            return

        order = next(
            (item for item in items if item.get("status") in ACTIVE_STATUSES),
            None,
        )
        if not order:
            await message.answer(
                "Сейчас активного заказа нет.",
                reply_markup=main_keyboard(),
            )
            return

        await message.answer(
            order_text(order),
            reply_markup=order_keyboard(order),
        )

    @router.message(F.text == "🔄 Обновить")
    async def refresh(message: Message) -> None:
        driver_id = await require_driver(message)
        if driver_id:
            await send_profile(message, driver_id)

    @router.message(Command("unlink"))
    @router.message(F.text == "🔗 Привязка")
    async def binding(message: Message) -> None:
        if not message.from_user:
            return
        link = await links.get(message.from_user.id)
        if not link:
            await message.answer(
                "Telegram пока не привязан к водителю.",
                reply_markup=contact_keyboard(),
            )
            return

        await message.answer(
            "<b>🔗 Привязка Telegram</b>\n\n"
            f"Driver ID: <code>{html.escape(link.driver_id)}</code>\n"
            f"Телефон: {html.escape(link.phone or '—')}\n"
            "Привязка хранится локально и восстанавливается после перезапуска.",
            reply_markup=binding_keyboard(),
        )

    @router.callback_query(F.data == "unlink:confirm")
    async def unlink_confirm(query: CallbackQuery) -> None:
        if query.message:
            await _safe_edit(
                query.message,
                "<b>Отвязать Telegram от профиля водителя?</b>\n\n"
                "После этого потребуется заново подтвердить номер телефона.",
                reply_markup=confirm_unlink_keyboard(),
            )
        await query.answer()

    @router.callback_query(F.data == "unlink:no")
    async def unlink_no(query: CallbackQuery) -> None:
        if query.message:
            await query.message.delete()
        await query.answer("Отменено")

    @router.callback_query(F.data == "unlink:yes")
    async def unlink_yes(query: CallbackQuery) -> None:
        await links.unlink(query.from_user.id)
        if query.message:
            await _safe_edit(
                query.message,
                "✅ Telegram отвязан от профиля водителя.",
            )
            await query.message.answer(
                "Чтобы привязать профиль снова, отправьте свой контакт.",
                reply_markup=contact_keyboard(),
            )
        await query.answer("Привязка удалена")

    @router.callback_query(F.data.startswith("orders:"))
    async def orders_page_callback(query: CallbackQuery) -> None:
        driver_id = await require_callback_driver(query)
        if not driver_id or not query.data or not query.message:
            return
        try:
            page = int(query.data.split(":", 1)[1])
        except ValueError:
            page = 0

        changed = await send_orders_page(
            query.message,
            driver_id,
            page=page,
            edit=True,
        )
        await query.answer("" if changed else "Без изменений")

    @router.callback_query(F.data.startswith("open:"))
    async def open_order(query: CallbackQuery) -> None:
        driver_id = await require_callback_driver(query)
        if not driver_id or not query.data or not query.message:
            return

        parts = query.data.split(":")
        order_id = parts[1]
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

        order = await get_owned_order(query, driver_id, order_id)
        if not order:
            return

        await _safe_edit(
            query.message,
            order_text(order),
            reply_markup=order_keyboard(order, page),
        )
        await query.answer()

    @router.callback_query(F.data.startswith("order:"))
    async def refresh_order(query: CallbackQuery) -> None:
        driver_id = await require_callback_driver(query)
        if not driver_id or not query.data or not query.message:
            return

        parts = query.data.split(":")
        order_id = parts[1]
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

        order = await get_owned_order(query, driver_id, order_id)
        if not order:
            return

        changed = await _safe_edit(
            query.message,
            order_text(order),
            reply_markup=order_keyboard(order, page),
        )
        await query.answer("" if changed else "Без изменений")

    @router.callback_query(F.data.startswith("complete:"))
    async def complete_order(query: CallbackQuery) -> None:
        driver_id = await require_callback_driver(query)
        if not driver_id or not query.data or not query.message:
            return

        parts = query.data.split(":")
        order_id = parts[1]
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

        current = await get_owned_order(query, driver_id, order_id)
        if not current:
            return

        try:
            order = await backend.complete_order(order_id)
        except BackendError as exc:
            await query.answer(str(exc), show_alert=True)
            return

        if str(order.get("driver_id")) != str(driver_id):
            await query.answer(
                "Backend вернул заказ другого водителя.",
                show_alert=True,
            )
            return

        await _safe_edit(
            query.message,
            order_text(order) + "\n\n✅ Заказ завершён в mock-режиме.",
            reply_markup=order_keyboard(order, page),
        )
        await query.answer("Заказ завершён")

    return router


async def run() -> None:
    settings = get_settings()
    if settings.TELEGRAM_BOT_MODE.lower() != "polling":
        raise RuntimeError(
            "python -m app.bot предназначен для TELEGRAM_BOT_MODE=polling. "
            "На PythonAnywhere используйте webhook-режим через FastAPI."
        )

    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN не задан. Добавьте токен в .env."
        )

    backend = BackendClient(
        settings.TELEGRAM_BOT_BACKEND_URL,
        settings.TELEGRAM_BOT_REQUEST_TIMEOUT_SECONDS,
    )
    links = DriverLinkStore(settings.TELEGRAM_BOT_DB_PATH)
    await links.init()

    bot = create_bot(
        settings.TELEGRAM_BOT_TOKEN,
        http_proxy=settings.TELEGRAM_HTTP_PROXY,
    )
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть бота"),
            BotCommand(command="profile", description="Профиль водителя"),
            BotCommand(command="orders", description="Заказы"),
            BotCommand(command="stats", description="Статистика"),
            BotCommand(command="unlink", description="Управление привязкой"),
        ]
    )
    await bot.delete_webhook(drop_pending_updates=False)

    dispatcher = Dispatcher()
    dispatcher.include_router(
        build_router(
            backend,
            links,
            mock_mode=settings.YANDEX_MOCK_MODE,
            page_size=max(settings.TELEGRAM_BOT_ORDERS_PAGE_SIZE, 1),
        )
    )

    logger.info(
        "Telegram bot starting; backend=%s mock=%s db=%s",
        settings.TELEGRAM_BOT_BACKEND_URL,
        settings.YANDEX_MOCK_MODE,
        settings.TELEGRAM_BOT_DB_PATH,
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
