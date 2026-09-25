from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from app.marketplace.pricing import estimate_price_details


_NOW = datetime.now(timezone.utc)


def _ts(minutes_ago: int) -> str:
    return (_NOW - timedelta(minutes=minutes_ago)).isoformat()


_RAW_OFFERS: list[dict[str, Any]] = [
    {
        "id": "market-2001",
        "driver_id": "driver-001",
        "source": "fasten",
        "source_title": "Fasten",
        "tariff": "comfort",
        "tariff_title": "Комфорт",
        "pickup_address": "Бишкек, ул. Киевская 120",
        "destination_address": "Бишкек, мкр. Асанбай",
        "distance_km": 8.6,
        "duration_minutes": 19,
        "source_price": None,
        "demand_multiplier": 1.15,
        "payment_method": "card",
        "status": "incoming",
        "status_title": "Новый заказ",
        "created_at": _ts(1),
        "expires_in_seconds": 42,
    },
    {
        "id": "market-2002",
        "driver_id": "driver-001",
        "source": "yandex",
        "source_title": "Яндекс",
        "tariff": "econom",
        "tariff_title": "Эконом",
        "pickup_address": "Бишкек, пр. Чуй 155",
        "destination_address": "Бишкек, 12 мкр",
        "distance_km": 6.1,
        "duration_minutes": 15,
        "source_price": 370.0,
        "demand_multiplier": 1.0,
        "payment_method": "cash",
        "status": "incoming",
        "status_title": "Новый заказ",
        "created_at": _ts(2),
        "expires_in_seconds": 31,
    },
    {
        "id": "market-2003",
        "driver_id": "driver-001",
        "source": "vezet",
        "source_title": "Везёт",
        "tariff": "econom",
        "tariff_title": "Эконом",
        "pickup_address": "Бишкек, ул. Токтогула 87",
        "destination_address": "Бишкек, Восток-5",
        "distance_km": 5.4,
        "duration_minutes": 14,
        "source_price": None,
        "demand_multiplier": 1.0,
        "payment_method": "cash",
        "status": "incoming",
        "status_title": "Новый заказ",
        "created_at": _ts(3),
        "expires_in_seconds": 50,
    },
    {
        "id": "market-2004",
        "driver_id": "driver-001",
        "source": "fasten",
        "source_title": "Fasten",
        "tariff": "business",
        "tariff_title": "Бизнес",
        "pickup_address": "Бишкек, аэропорт Манас",
        "destination_address": "Бишкек, ул. Ибраимова 103",
        "distance_km": 28.2,
        "duration_minutes": 37,
        "source_price": 1680.0,
        "demand_multiplier": 1.0,
        "payment_method": "card",
        "status": "incoming",
        "status_title": "Новый заказ",
        "created_at": _ts(5),
        "expires_in_seconds": 55,
    },
    {
        "id": "market-2005",
        "driver_id": "driver-001",
        "source": "yandex",
        "source_title": "Яндекс",
        "tariff": "comfort",
        "tariff_title": "Комфорт",
        "pickup_address": "Бишкек, ул. Московская 88",
        "destination_address": "Бишкек, ул. Ахунбаева 92",
        "distance_km": 7.9,
        "duration_minutes": 20,
        "source_price": 540.0,
        "demand_multiplier": 1.0,
        "payment_method": "card",
        "status": "accepted",
        "status_title": "Принят",
        "created_at": _ts(12),
        "expires_in_seconds": None,
    },
    {
        "id": "market-2006",
        "driver_id": "driver-001",
        "source": "vezet",
        "source_title": "Везёт",
        "tariff": "comfort",
        "tariff_title": "Комфорт",
        "pickup_address": "Бишкек, ул. Манаса 40",
        "destination_address": "Бишкек, мкр. Джал",
        "distance_km": 9.2,
        "duration_minutes": 24,
        "source_price": None,
        "demand_multiplier": 1.2,
        "payment_method": "cash",
        "status": "incoming",
        "status_title": "Новый заказ",
        "created_at": _ts(7),
        "expires_in_seconds": 47,
    },
    {
        "id": "market-2007",
        "driver_id": "driver-001",
        "source": "fasten",
        "source_title": "Fasten",
        "tariff": "econom",
        "tariff_title": "Эконом",
        "pickup_address": "Бишкек, ТРЦ Asia Mall",
        "destination_address": "Бишкек, Аламедин-1",
        "distance_km": 10.7,
        "duration_minutes": 26,
        "source_price": None,
        "demand_multiplier": 1.0,
        "payment_method": "card",
        "status": "incoming",
        "status_title": "Новый заказ",
        "created_at": _ts(9),
        "expires_in_seconds": 36,
    },
    {
        "id": "market-2008",
        "driver_id": "driver-001",
        "source": "yandex",
        "source_title": "Яндекс",
        "tariff": "comfort_plus",
        "tariff_title": "Комфорт+",
        "pickup_address": "Бишкек, ул. Байтик Баатыра 34",
        "destination_address": "Бишкек, аэропорт Манас",
        "distance_km": 30.5,
        "duration_minutes": 42,
        "source_price": 1510.0,
        "demand_multiplier": 1.0,
        "payment_method": "card",
        "status": "incoming",
        "status_title": "Новый заказ",
        "created_at": _ts(10),
        "expires_in_seconds": 29,
    },
]


def list_mock_marketplace_orders() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for raw in _RAW_OFFERS:
        item = deepcopy(raw)
        exact_price = item.pop("source_price")
        estimated = exact_price is None
        calculation = None
        if estimated:
            calculation = estimate_price_details(
                source=item["source"],
                tariff=item["tariff"],
                distance_km=float(item["distance_km"]),
                duration_minutes=int(item["duration_minutes"]),
                demand_multiplier=float(item.get("demand_multiplier") or 1.0),
            )
            price = float(calculation["total"])
        else:
            price = float(exact_price)

        item["price"] = price
        item["price_calculation"] = calculation
        item["currency"] = "KGS"
        item["price_is_estimated"] = estimated
        item["price_label"] = (
            f"≈ {price:.0f} сом" if estimated else f"{price:.0f} сом"
        )
        item["can_accept"] = item.get("status") == "incoming"
        result.append(item)
    return result


def accept_mock_marketplace_order(
    order_id: str,
    *,
    driver_id: str,
) -> dict[str, Any] | None:
    for raw in _RAW_OFFERS:
        if raw["id"] != order_id:
            continue
        if raw["driver_id"] != driver_id:
            return None
        if raw["status"] != "incoming":
            raise ValueError("Заказ уже недоступен для принятия.")

        raw["status"] = "accepted"
        raw["status_title"] = "Принят"
        raw["expires_in_seconds"] = None
        raw["accepted_at"] = datetime.now(timezone.utc).isoformat()

        for item in list_mock_marketplace_orders():
            if item["id"] == order_id:
                item["can_accept"] = False
                return item
        return None
    return None
