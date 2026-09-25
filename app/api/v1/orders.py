from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

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
    }


@router.get("/orders/{order_id}")
async def get_order(order_id: str) -> dict[str, Any]:
    return {"order": {"id": order_id}, "filter_result": None, "driver": None}


@router.post("/orders/sync")
async def sync_orders() -> dict[str, str]:
    return {"status": "scheduled"}


@router.post("/orders/{order_id}/evaluate")
async def evaluate_order(order_id: str) -> dict[str, Any]:
    return {"order_id": order_id, "decision": "acceptable", "reasons": []}


@router.get("/orders/{order_id}/filter-history")
async def filter_history(order_id: str) -> dict[str, Any]:
    return {"order_id": order_id, "history": []}
