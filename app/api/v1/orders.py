from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.mock_data import complete_order as complete_mock_order
from app.mock_data import get_order as get_mock_order
from app.mock_data import list_orders as list_mock_orders

router = APIRouter(prefix="/api/v1", tags=["orders"])


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
    settings = get_settings()

    if settings.YANDEX_MOCK_MODE:
        all_items = list_mock_orders(driver_id=driver_id, status=status)
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
            "mock": True,
        }

    return {
        "items": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
        "filters": {
            "driver_id": driver_id,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "filter_decision": filter_decision,
        },
        "mock": False,
    }


@router.get("/orders/{order_id}")
async def get_order(order_id: str) -> dict[str, Any]:
    settings = get_settings()
    if settings.YANDEX_MOCK_MODE:
        order = get_mock_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="Заказ не найден.")
        return {
            "order": order,
            "filter_result": None,
            "driver": None,
            "mock": True,
        }

    return {
        "order": {"id": order_id},
        "filter_result": None,
        "driver": None,
        "mock": False,
    }


@router.post("/orders/{order_id}/complete")
async def complete_order(order_id: str) -> dict[str, Any]:
    settings = get_settings()

    if not settings.YANDEX_MOCK_MODE:
        raise HTTPException(
            status_code=501,
            detail=(
                "Завершение реального заказа не реализовано: "
                "в публичном Yandex Fleet API нет документированного "
                "универсального метода завершения заказа водителя."
            ),
        )

    try:
        order = complete_mock_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден.")

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
