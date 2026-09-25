from __future__ import annotations

import html
from datetime import datetime
from typing import Any


STATUS_TITLES = {
    "assigned": "Назначен",
    "waiting": "Ожидание",
    "in_progress": "В поездке",
    "completed": "Завершён",
    "cancelled": "Отменён",
}

PAYMENT_TITLES = {
    "card": "Карта",
    "cash": "Наличные",
    "corporate": "Корпоративный",
}

CATEGORY_TITLES = {
    "econom": "Эконом",
    "comfort": "Комфорт",
    "comfort_plus": "Комфорт+",
    "business": "Бизнес",
}


def esc(value: Any) -> str:
    return html.escape(str(value if value not in (None, "") else "—"))


def money(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return esc(value)


def datetime_text(value: Any) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return esc(value)


def driver_profile_text(
    driver: dict[str, Any],
    summary: dict[str, Any] | None = None,
) -> str:
    name = driver.get("full_name") or " ".join(
        part
        for part in (driver.get("first_name"), driver.get("last_name"))
        if part
    ).strip()
    vehicle = driver.get("vehicle") or {}
    tariffs = ", ".join(driver.get("tariffs") or []) or "—"

    lines = [
        "<b>Профиль водителя</b>",
        "",
        f"<b>{esc(name)}</b>",
        f"Телефон: {esc(driver.get('phone'))}",
        f"Статус: {esc(driver.get('work_rule') or driver.get('status'))}",
        f"Рейтинг: {esc(driver.get('rating'))}",
        f"Приоритет: {esc(driver.get('priority_points'))}",
        f"Баланс: {money(driver.get('balance'))} {esc(driver.get('currency') or 'KGS')}",
        f"Тарифы: {esc(tariffs)}",
        "",
        "<b>Автомобиль</b>",
        f"{esc(vehicle.get('brand'))} {esc(vehicle.get('model'))}, {esc(vehicle.get('year'))}",
        f"Цвет: {esc(vehicle.get('color'))}",
        f"Госномер: {esc(vehicle.get('plate'))}",
    ]

    if summary:
        lines.extend(
            [
                "",
                "<b>Текущая статистика</b>",
                f"Активных: {esc(summary.get('active_orders'))}",
                f"Завершено: {esc(summary.get('completed_orders'))}",
                f"Отменено: {esc(summary.get('cancelled_orders'))}",
                f"Заработок: {money(summary.get('earnings'))} {esc(summary.get('currency') or 'KGS')}",
                f"Пройдено: {esc(summary.get('distance_km'))} км",
            ]
        )

    return "\n".join(lines)


def stats_text(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "<b>Статистика водителя</b>",
            "",
            f"Всего заказов: {esc(summary.get('orders_total'))}",
            f"Активных: {esc(summary.get('active_orders'))}",
            f"Завершено: {esc(summary.get('completed_orders'))}",
            f"Отменено: {esc(summary.get('cancelled_orders'))}",
            f"Заработок: {money(summary.get('earnings'))} {esc(summary.get('currency') or 'KGS')}",
            f"Дистанция: {esc(summary.get('distance_km'))} км",
        ]
    )


def order_text(order: dict[str, Any]) -> str:
    status = order.get("status")
    status_title = order.get("status_title") or STATUS_TITLES.get(status, status)
    category = CATEGORY_TITLES.get(order.get("category"), order.get("category"))
    payment = PAYMENT_TITLES.get(
        order.get("payment_method"),
        order.get("payment_method"),
    )

    return "\n".join(
        [
            f"<b>Заказ {esc(order.get('id'))}</b>",
            "",
            f"Статус: <b>{esc(status_title)}</b>",
            f"Тариф: {esc(category)}",
            f"Оплата: {esc(payment)}",
            f"Стоимость: <b>{money(order.get('price'))} {esc(order.get('currency') or 'KGS')}</b>",
            "",
            f"Откуда: {esc(order.get('pickup') or order.get('pickup_address'))}",
            f"Куда: {esc(order.get('destination') or order.get('destination_address'))}",
            "",
            f"Расстояние: {esc(order.get('distance_km'))} км",
            f"Время: {esc(order.get('duration_minutes'))} мин",
            f"Создан: {datetime_text(order.get('created_at') or order.get('yandex_created_at'))}",
            f"Начат: {datetime_text(order.get('started_at'))}",
            f"Завершён: {datetime_text(order.get('completed_at'))}",
        ]
    )


def order_list_line(order: dict[str, Any]) -> str:
    status = order.get("status")
    status_title = order.get("status_title") or STATUS_TITLES.get(status, status)
    return (
        f"{esc(status_title)} · {money(order.get('price'))} "
        f"{esc(order.get('currency') or 'KGS')} · "
        f"{esc(order.get('pickup') or order.get('pickup_address'))}"
    )
