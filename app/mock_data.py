from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any


_NOW = datetime.now(timezone.utc)


def _ts(minutes_ago: int) -> str:
    return (_NOW - timedelta(minutes=minutes_ago)).isoformat()


_DRIVERS: dict[str, dict[str, Any]] = {
    "driver-001": {
        "id": "driver-001",
        "yandex_driver_id": "driver-001",
        "full_name": "Тестовый водитель",
        "first_name": "Тестовый",
        "last_name": "Водитель",
        "phone": "+996555000001",
        "status": "working",
        "local_driver_state": "WORKING",
        "rating": 4.96,
        "balance": 4250.0,
        "currency": "KGS",
        "priority_points": 14,
        "work_rule": "На линии",
        "tariffs": ["Эконом", "Комфорт"],
        "vehicle": {
            "id": "vehicle-001",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2021,
            "color": "Белый",
            "plate": "01 KG 123 ABC",
            "category": "comfort",
        },
        "car": "Toyota Camry • 01 KG 123 ABC",
        "is_enabled": True,
    },
    "driver-002": {
        "id": "driver-002",
        "yandex_driver_id": "driver-002",
        "full_name": "Второй водитель",
        "first_name": "Второй",
        "last_name": "Водитель",
        "phone": "+996555000002",
        "status": "free",
        "local_driver_state": "FREE",
        "rating": 4.91,
        "balance": 2180.0,
        "currency": "KGS",
        "priority_points": 9,
        "work_rule": "Свободен",
        "tariffs": ["Эконом"],
        "vehicle": {
            "id": "vehicle-002",
            "brand": "Hyundai",
            "model": "Sonata",
            "year": 2020,
            "color": "Серый",
            "plate": "01 KG 456 ABC",
            "category": "econom",
        },
        "car": "Hyundai Sonata • 01 KG 456 ABC",
        "is_enabled": True,
    },
}


_ORDERS: dict[str, dict[str, Any]] = {
    "order-1006": {
        "id": "order-1006",
        "yandex_order_id": "order-1006",
        "driver_id": "driver-001",
        "status": "in_progress",
        "status_title": "В поездке",
        "pickup": "Бишкек, пр. Чуй 120",
        "pickup_address": "Бишкек, пр. Чуй 120",
        "destination": "Бишкек, ул. Ахунбаева 92",
        "destination_address": "Бишкек, ул. Ахунбаева 92",
        "price": 520.0,
        "currency": "KGS",
        "category": "comfort",
        "payment_method": "card",
        "distance_km": 8.4,
        "duration_minutes": 24,
        "created_at": _ts(18),
        "yandex_created_at": _ts(18),
        "started_at": _ts(12),
        "completed_at": None,
        "can_complete": True,
    },
    "order-1005": {
        "id": "order-1005",
        "yandex_order_id": "order-1005",
        "driver_id": "driver-001",
        "status": "completed",
        "status_title": "Завершён",
        "pickup": "Бишкек, ул. Киевская 55",
        "pickup_address": "Бишкек, ул. Киевская 55",
        "destination": "Бишкек, мкр. Асанбай",
        "destination_address": "Бишкек, мкр. Асанбай",
        "price": 430.0,
        "currency": "KGS",
        "category": "econom",
        "payment_method": "cash",
        "distance_km": 7.2,
        "duration_minutes": 21,
        "created_at": _ts(75),
        "yandex_created_at": _ts(75),
        "started_at": _ts(68),
        "completed_at": _ts(47),
        "can_complete": False,
    },
    "order-1004": {
        "id": "order-1004",
        "yandex_order_id": "order-1004",
        "driver_id": "driver-001",
        "status": "completed",
        "status_title": "Завершён",
        "pickup": "Бишкек, ул. Токтогула 125",
        "pickup_address": "Бишкек, ул. Токтогула 125",
        "destination": "Бишкек, Восток-5",
        "destination_address": "Бишкек, Восток-5",
        "price": 610.0,
        "currency": "KGS",
        "category": "comfort",
        "payment_method": "card",
        "distance_km": 10.1,
        "duration_minutes": 29,
        "created_at": _ts(130),
        "yandex_created_at": _ts(130),
        "started_at": _ts(122),
        "completed_at": _ts(93),
        "can_complete": False,
    },
    "order-1003": {
        "id": "order-1003",
        "yandex_order_id": "order-1003",
        "driver_id": "driver-001",
        "status": "completed",
        "status_title": "Завершён",
        "pickup": "Бишкек, Манаса 40",
        "pickup_address": "Бишкек, Манаса 40",
        "destination": "Бишкек, Аламедин-1",
        "destination_address": "Бишкек, Аламедин-1",
        "price": 390.0,
        "currency": "KGS",
        "category": "econom",
        "payment_method": "card",
        "distance_km": 6.3,
        "duration_minutes": 19,
        "created_at": _ts(185),
        "yandex_created_at": _ts(185),
        "started_at": _ts(179),
        "completed_at": _ts(160),
        "can_complete": False,
    },
    "order-1002": {
        "id": "order-1002",
        "yandex_order_id": "order-1002",
        "driver_id": "driver-001",
        "status": "cancelled",
        "status_title": "Отменён",
        "pickup": "Бишкек, ул. Московская 88",
        "pickup_address": "Бишкек, ул. Московская 88",
        "destination": "Бишкек, 12 мкр",
        "destination_address": "Бишкек, 12 мкр",
        "price": 0.0,
        "currency": "KGS",
        "category": "econom",
        "payment_method": "cash",
        "distance_km": None,
        "duration_minutes": None,
        "created_at": _ts(230),
        "yandex_created_at": _ts(230),
        "started_at": None,
        "completed_at": None,
        "can_complete": False,
    },
    "order-1001": {
        "id": "order-1001",
        "yandex_order_id": "order-1001",
        "driver_id": "driver-001",
        "status": "completed",
        "status_title": "Завершён",
        "pickup": "Бишкек, ул. Ибраимова 103",
        "pickup_address": "Бишкек, ул. Ибраимова 103",
        "destination": "Бишкек, Джал",
        "destination_address": "Бишкек, Джал",
        "price": 470.0,
        "currency": "KGS",
        "category": "econom",
        "payment_method": "cash",
        "distance_km": 7.9,
        "duration_minutes": 23,
        "created_at": _ts(310),
        "yandex_created_at": _ts(310),
        "started_at": _ts(304),
        "completed_at": _ts(281),
        "can_complete": False,
    },
}


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 9:
        digits = "996" + digits
    return f"+{digits}"


def list_drivers() -> list[dict[str, Any]]:
    return deepcopy(list(_DRIVERS.values()))


def get_driver(driver_id: str) -> dict[str, Any] | None:
    driver = _DRIVERS.get(driver_id)
    return deepcopy(driver) if driver else None


def get_driver_by_phone(phone: str) -> dict[str, Any] | None:
    normalized = normalize_phone(phone)
    for driver in _DRIVERS.values():
        if driver.get("phone") == normalized:
            return deepcopy(driver)
    return None


def list_orders(
    *,
    driver_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    items = list(_ORDERS.values())
    if driver_id:
        items = [item for item in items if item.get("driver_id") == driver_id]
    if status:
        items = [item for item in items if item.get("status") == status]
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return deepcopy(items)


def get_order(order_id: str) -> dict[str, Any] | None:
    order = _ORDERS.get(order_id)
    return deepcopy(order) if order else None


def get_driver_summary(driver_id: str) -> dict[str, Any] | None:
    driver = get_driver(driver_id)
    if not driver:
        return None

    orders = list_orders(driver_id=driver_id)
    completed = [order for order in orders if order["status"] == "completed"]
    active = [
        order
        for order in orders
        if order["status"] in {"assigned", "waiting", "in_progress"}
    ]

    earnings = sum(float(order.get("price") or 0) for order in completed)
    total_distance = sum(float(order.get("distance_km") or 0) for order in completed)

    return {
        "driver_id": driver_id,
        "active_orders": len(active),
        "completed_orders": len(completed),
        "cancelled_orders": len(
            [order for order in orders if order["status"] == "cancelled"]
        ),
        "earnings": round(earnings, 2),
        "currency": driver.get("currency", "KGS"),
        "distance_km": round(total_distance, 1),
        "orders_total": len(orders),
    }


def complete_order(order_id: str) -> dict[str, Any] | None:
    order = _ORDERS.get(order_id)
    if order is None:
        return None
    if order["status"] == "completed":
        return deepcopy(order)
    if not order.get("can_complete", False):
        raise ValueError("Этот mock-заказ нельзя завершить.")

    order["status"] = "completed"
    order["status_title"] = "Завершён"
    order["completed_at"] = datetime.now(timezone.utc).isoformat()
    order["can_complete"] = False
    return deepcopy(order)
