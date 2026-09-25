from __future__ import annotations

from typing import Any

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📱 Поделиться номером",
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 Профиль"),
                KeyboardButton(text="📦 Заказы"),
            ],
            [
                KeyboardButton(text="📊 Статистика"),
                KeyboardButton(text="🚕 Активный заказ"),
            ],
            [
                KeyboardButton(text="🔄 Обновить"),
                KeyboardButton(text="🔗 Привязка"),
            ],
        ],
        resize_keyboard=True,
    )


def binding_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отвязать Telegram",
                    callback_data="unlink:confirm",
                )
            ]
        ]
    )


def confirm_unlink_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, отвязать",
                    callback_data="unlink:yes",
                ),
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data="unlink:no",
                ),
            ]
        ]
    )


def order_keyboard(order: dict[str, Any], page: int = 0) -> InlineKeyboardMarkup:
    order_id = str(order["id"])
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🔄 Обновить заказ",
                callback_data=f"order:{order_id}:{page}",
            )
        ]
    ]

    if order.get("can_complete") and order.get("status") != "completed":
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Завершить заказ",
                    callback_data=f"complete:{order_id}:{page}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ К списку заказов",
                callback_data=f"orders:{page}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def orders_keyboard(
    orders: list[dict[str, Any]],
    *,
    page: int,
    page_size: int,
    total: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for order in orders:
        status = order.get("status_title") or order.get("status") or "Заказ"
        price = order.get("price")
        price_text = "—" if price is None else f"{float(price):.0f}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} · {price_text} {order.get('currency', 'KGS')}",
                    callback_data=f"open:{order['id']}:{page}",
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"orders:{page - 1}",
            )
        )

    if (page + 1) * page_size < total:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"orders:{page + 1}",
            )
        )

    if nav:
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить список",
                callback_data=f"orders:{page}",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)
