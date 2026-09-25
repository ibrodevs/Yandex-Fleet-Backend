from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.services.fleet import FleetProviderError, get_fleet_provider

router = APIRouter(prefix="/api/v1", tags=["orders"])


def _provider_error(exc: FleetProviderError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/orders")
async def list_orders(
    driver_id: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    filter_decision: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    try:
        all_items = await get_fleet_provider().list_orders(
            driver_id=driver_id,
            status=status,
        )
    except FleetProviderError as exc:
        raise _provider_error(exc) from exc

    items = all_items[offset : offset + limit]
    return {
        "items": items,
        "total": len(all_items),
        "limit": limit,
        "offset": offset,
        "filters": {
            "driver_id": driver_id,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "filter_decision": filter_decision,
        },
        "mock": get_settings().YANDEX_MOCK_MODE,
    }


@router.get("/orders/{order_id}")
async def get_order(order_id: str) -> dict[str, Any]:
    try:
        order = await get_fleet_provider().get_order(order_id)
    except FleetProviderError as exc:
        raise _provider_error(exc) from exc

    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден.")

    return {
        "order": order,
        "filter_result": None,
        "driver": None,
        "mock": get_settings().YANDEX_MOCK_MODE,
    }


@router.post("/orders/{order_id}/complete")
async def complete_order(order_id: str) -> dict[str, Any]:
    if not get_settings().YANDEX_MOCK_MODE:
        raise HTTPException(
            status_code=501,
            detail=(
                "Завершение реального заказа не реализовано: "
                "публичный Fleet API не предоставляет универсальную "
                "операцию завершения заказа водителя."
            ),
        )

    try:
        order = await get_fleet_provider().complete_order(order_id)
    except FleetProviderError as exc:
        message = str(exc)
        status_code = 404 if "не найден" in message.lower() else 409
        raise HTTPException(status_code=status_code, detail=message) from exc

    return {"order": order, "mock": True}


@router.post("/orders/sync")
async def sync_orders() -> dict[str, str]:
    return {"status": "scheduled"}


@router.post("/orders/{order_id}/evaluate")
async def evaluate_order(order_id: str) -> dict[str, Any]:
    return {
        "order_id": order_id,
        "decision": "acceptable",
        "reasons": [],
    }


@router.get("/orders/{order_id}/filter-history")
async def filter_history(order_id: str) -> dict[str, Any]:
    return {"order_id": order_id, "history": []}
