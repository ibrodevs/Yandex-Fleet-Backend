from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.fleet.phone import normalize_phone

YANDEX_ORDER_STATUS_MAP = {
    "none": "unknown",
    "driving": "assigned",
    "waiting": "waiting",
    "transporting": "in_progress",
    "complete": "completed",
    "cancelled": "cancelled",
    "calling": "cancelled",
    "expired": "cancelled",
    "failed": "cancelled",
}

ORDER_STATUS_TITLES = {
    "unknown": "Неизвестен",
    "assigned": "Назначен",
    "waiting": "Ожидание",
    "in_progress": "В поездке",
    "completed": "Завершён",
    "cancelled": "Отменён",
}

CATEGORY_TITLES = {
    "econom": "Эконом",
    "comfort": "Комфорт",
    "comfort_plus": "Комфорт+",
    "business": "Бизнес",
    "minivan": "Минивэн",
    "vip": "VIP",
    "express": "Доставка",
    "cargo": "Грузовой",
}

PAYMENT_METHOD_MAP = {
    "cash": "cash",
    "cashless": "card",
    "card": "card",
    "internal": "other",
    "other": "other",
    "corp": "corporate",
    "prepaid": "card",
}


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _duration_minutes(start: Any, end: Any) -> int | None:
    if not start or not end:
        return None
    try:
        started = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        ended = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    seconds = (ended - started).total_seconds()
    return max(0, round(seconds / 60))


def map_yandex_vehicle(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    categories = raw.get("category") or raw.get("categories") or []
    if not isinstance(categories, list):
        categories = [categories]
    return {
        "id": str(raw["id"]),
        "status": raw.get("status"),
        "brand": raw.get("brand"),
        "model": raw.get("model"),
        "year": raw.get("year"),
        "color": raw.get("color"),
        "plate": raw.get("number") or (raw.get("license") or {}).get("number"),
        "callsign": raw.get("callsign"),
        "categories": [str(item) for item in categories if item],
    }


def map_yandex_driver(
    raw: dict[str, Any],
    *,
    default_country_code: str = "996",
) -> dict[str, Any]:
    profile = raw.get("driver_profile") or {}
    current_status = raw.get("current_status") or {}
    accounts = raw.get("accounts") or []
    current_account = next(
        (item for item in accounts if isinstance(item, dict) and item.get("type") == "current"),
        next((item for item in accounts if isinstance(item, dict)), {}),
    )
    vehicle = map_yandex_vehicle(raw.get("car"))
    phones = [
        normalized
        for value in (profile.get("phones") or [])
        if (normalized := normalize_phone(value, default_country_code=default_country_code))
    ]
    name_parts = [
        profile.get("last_name"),
        profile.get("first_name"),
        profile.get("middle_name"),
    ]
    full_name = " ".join(str(part) for part in name_parts if part).strip() or None
    categories = (vehicle or {}).get("categories") or []

    return {
        "id": str(profile.get("id") or ""),
        "yandex_driver_id": str(profile.get("id") or ""),
        "full_name": full_name,
        "first_name": profile.get("first_name"),
        "last_name": profile.get("last_name"),
        "middle_name": profile.get("middle_name"),
        "phone": phones[0] if phones else None,
        "phones": phones,
        "status": profile.get("work_status"),
        "work_status": profile.get("work_status"),
        "local_driver_state": current_status.get("status"),
        "rating": None,
        "priority_points": None,
        "balance": _number(current_account.get("balance")),
        "currency": current_account.get("currency"),
        "work_rule": profile.get("work_status"),
        "work_rule_id": profile.get("work_rule_id"),
        "tariffs": [CATEGORY_TITLES.get(item, item) for item in categories],
        "vehicle": vehicle,
        "car": " · ".join(
            item
            for item in (
                " ".join(
                    str(value)
                    for value in ((vehicle or {}).get("brand"), (vehicle or {}).get("model"))
                    if value
                ).strip(),
                str((vehicle or {}).get("plate") or ""),
            )
            if item
        ) or None,
        "is_enabled": profile.get("work_status") == "working",
        "provider": "yandex",
    }


def _event_time(raw: dict[str, Any], statuses: set[str]) -> Any:
    for event in raw.get("events") or []:
        if isinstance(event, dict) and event.get("order_status") in statuses:
            return event.get("event_at")
    return None


def map_yandex_order(raw: dict[str, Any]) -> dict[str, Any]:
    yandex_status = str(raw.get("status") or "none")
    status = YANDEX_ORDER_STATUS_MAP.get(yandex_status, "unknown")
    driver = raw.get("driver_profile") or {}
    car = raw.get("car") or {}
    route_points = [item for item in (raw.get("route_points") or []) if isinstance(item, dict)]
    pickup = (raw.get("address_from") or {}).get("address")
    destination = route_points[-1].get("address") if route_points else None
    booked_at = raw.get("booked_at")
    ended_at = raw.get("ended_at")
    started_at = _event_time(raw, {"transporting", "driving"})
    mileage = _number(raw.get("mileage"))
    category = str(raw.get("category") or "") or None
    payment_method = str(raw.get("payment_method") or "") or None

    return {
        "id": str(raw.get("id") or ""),
        "yandex_order_id": str(raw.get("id") or ""),
        "short_id": raw.get("short_id"),
        "driver_id": str(driver.get("id")) if driver.get("id") else None,
        "status": status,
        "status_title": ORDER_STATUS_TITLES[status],
        "yandex_status": yandex_status,
        "category": category,
        "tariff": category,
        "tariff_title": CATEGORY_TITLES.get(category or "", category),
        "payment_method": PAYMENT_METHOD_MAP.get(payment_method or "", payment_method),
        "price": _number(raw.get("price")),
        "currency": None,
        "pickup": pickup,
        "pickup_address": pickup,
        "destination": destination,
        "destination_address": destination,
        "route_points": route_points,
        "distance_km": mileage,
        "duration_minutes": _duration_minutes(booked_at, ended_at),
        "created_at": raw.get("created_at"),
        "yandex_created_at": raw.get("created_at"),
        "booked_at": booked_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "completed_at": ended_at if status == "completed" else None,
        "vehicle": {
            "id": car.get("id"),
            "brand_model": car.get("brand_model"),
            "plate": (car.get("license") or {}).get("number"),
            "callsign": car.get("callsign"),
        }
        if car
        else None,
        "driver": {"id": driver.get("id"), "name": driver.get("name")} if driver else None,
        "provider": raw.get("provider") or "yandex",
        "source": "yandex",
        "source_title": "Яндекс",
        "price_is_estimated": False,
        "price_calculation": None,
        "can_accept": False,
        "can_complete": False,
        "cancellation_description": raw.get("cancellation_description"),
    }


def map_yandex_driver_summary(
    driver_id: str,
    orders: list[dict[str, Any]],
    *,
    currency: str | None = None,
) -> dict[str, Any]:
    owned = [order for order in orders if str(order.get("driver_id")) == str(driver_id)]
    completed = [order for order in owned if order.get("status") == "completed"]
    active = [
        order
        for order in owned
        if order.get("status") in {"assigned", "waiting", "in_progress"}
    ]
    known_prices = [float(order["price"]) for order in completed if order.get("price") is not None]
    known_distances = [
        float(order["distance_km"])
        for order in completed
        if order.get("distance_km") is not None
    ]
    return {
        "driver_id": driver_id,
        "active_orders": len(active),
        "completed_orders": len(completed),
        "cancelled_orders": len([order for order in owned if order.get("status") == "cancelled"]),
        "earnings": round(sum(known_prices), 2) if known_prices else None,
        "currency": currency,
        "distance_km": round(sum(known_distances), 1) if known_distances else None,
        "orders_total": len(owned),
    }
