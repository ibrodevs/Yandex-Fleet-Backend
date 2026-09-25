from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["drivers"])


@router.get("/drivers")
async def list_drivers() -> dict[str, Any]:
    return {"items": [], "total": 0}


@router.get("/drivers/{driver_id}")
async def get_driver(driver_id: str) -> dict[str, Any]:
    return {"id": driver_id, "yandex_driver_id": driver_id, "is_enabled": True}


@router.get("/drivers/{driver_id}/filter-settings")
async def get_filter_settings(driver_id: str) -> dict[str, Any]:
    return {"driver_id": driver_id, "enabled": True, "min_price": None}


@router.put("/drivers/{driver_id}/filter-settings")
async def update_filter_settings(driver_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"driver_id": driver_id, "updated": True, "settings": payload}
