from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


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
        "car": "Hyundai Sonata • 01 KG 456 ABC",
        "is_enabled": True,
    },
}

_NOW = datetime.now(timezone.utc).isoformat()

_ORDERS: dict[str, dict[str, Any]] = {
    "order-1001": {
        "id": "order-1001",
        "yandex_order_id": "order-1001",
        "driver_id": "driver-001",
        "status": "in_progress",
        "pickup": "Бишкек, пр. Чуй 120",
        "pickup_address": "Бишкек, пр. Чуй 120",
        "destination": "Бишкек, ул. Ахунбаева 92",
        "destination_address": "Бишкек, ул. Ахунбаева 92",
        "price": 520.0,
        "currency": "KGS",
        "category": "econom",
        "created_at": _NOW,
        "yandex_created_at": _NOW,
        "can_complete": True,
    },
    "order-1000": {
        "id": "order-1000",
        "yandex_order_id": "order-1000",
        "driver_id": "driver-001",
        "status": "completed",
        "pickup": "Бишкек, ул. Киевская 55",
        "pickup_address": "Бишкек, ул. Киевская 55",
        "destination": "Бишкек, мкр. Асанбай",
        "destination_address": "Бишкек, мкр. Асанбай",
        "price": 430.0,
        "currency": "KGS",
        "category": "econom",
        "created_at": _NOW,
        "yandex_created_at": _NOW,
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
    return deepcopy(items)


def get_order(order_id: str) -> dict[str, Any] | None:
    order = _ORDERS.get(order_id)
    return deepcopy(order) if order else None


def complete_order(order_id: str) -> dict[str, Any] | None:
    order = _ORDERS.get(order_id)
    if order is None:
        return None
    if order["status"] == "completed":
        return deepcopy(order)
    if not order.get("can_complete", False):
        raise ValueError("Этот mock-заказ нельзя завершить.")
    order["status"] = "completed"
    order["can_complete"] = False
    return deepcopy(order)
