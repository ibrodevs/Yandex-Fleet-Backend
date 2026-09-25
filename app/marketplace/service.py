from __future__ import annotations

from typing import Any

from app.marketplace.mock import (
    accept_mock_marketplace_order,
    list_mock_marketplace_orders,
)


SOURCE_TITLES = {
    "fasten": "Fasten",
    "yandex": "Яндекс",
    "vezet": "Везёт",
}


def list_marketplace_orders(
    *,
    driver_id: str,
    source: str | None = None,
    status: str | None = None,
    tariff: str | None = None,
) -> list[dict[str, Any]]:
    items = [
        item
        for item in list_mock_marketplace_orders()
        if item["driver_id"] == driver_id
    ]
    if source:
        items = [item for item in items if item["source"] == source]
    if status:
        items = [item for item in items if item["status"] == status]
    if tariff:
        items = [item for item in items if item["tariff"] == tariff]
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items


def get_marketplace_order(
    order_id: str,
    *,
    driver_id: str | None = None,
) -> dict[str, Any] | None:
    for item in list_mock_marketplace_orders():
        if item["id"] != order_id:
            continue
        if driver_id and item["driver_id"] != driver_id:
            return None
        return item
    return None


def get_marketplace_summary(driver_id: str) -> dict[str, Any]:
    items = list_marketplace_orders(driver_id=driver_id)
    incoming = [item for item in items if item["status"] == "incoming"]
    estimated = [item for item in incoming if item["price_is_estimated"]]
    exact = [item for item in incoming if not item["price_is_estimated"]]

    by_source = {
        source: len([item for item in incoming if item["source"] == source])
        for source in SOURCE_TITLES
    }

    prices = [float(item["price"]) for item in incoming]
    return {
        "driver_id": driver_id,
        "incoming_count": len(incoming),
        "accepted_count": len(
            [item for item in items if item["status"] == "accepted"]
        ),
        "estimated_price_count": len(estimated),
        "exact_price_count": len(exact),
        "average_incoming_price": (
            round(sum(prices) / len(prices), 0) if prices else 0
        ),
        "currency": "KGS",
        "by_source": by_source,
        "sources": [
            {"id": key, "title": title}
            for key, title in SOURCE_TITLES.items()
        ],
    }


def accept_marketplace_order(
    order_id: str,
    *,
    driver_id: str,
) -> dict[str, Any]:
    try:
        order = accept_mock_marketplace_order(
            order_id,
            driver_id=driver_id,
        )
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    if not order:
        raise LookupError("Заказ не найден.")
    return order
