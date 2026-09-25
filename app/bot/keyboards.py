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
                KeyboardButton(text="🔄 Обновить"),
                KeyboardButton(text="🚪 Выйти"),
            ],
        ],
        resize_keyboard=True,
    )


def order_keyboard(order: dict[str, Any]) -> InlineKeyboardMarkup:
    order_id = str(order["id"])
    rows = [
        [
            InlineKeyboardButton(
                text="🔎 Обновить",
                callback_data=f"order:{order_id}",
            )
        ]
    ]
    if order.get("can_complete") and order.get("status") != "completed":
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Завершить заказ",
                    callback_data=f"complete:{order_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
