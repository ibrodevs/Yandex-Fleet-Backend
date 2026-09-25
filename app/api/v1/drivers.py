from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.mock_data import get_driver as get_mock_driver
from app.mock_data import get_driver_by_phone as get_mock_driver_by_phone
from app.mock_data import list_drivers as list_mock_drivers

router = APIRouter(prefix="/api/v1", tags=["drivers"])


@router.get("/drivers")
async def list_drivers() -> dict[str, Any]:
    settings = get_settings()
    if settings.YANDEX_MOCK_MODE:
        items = list_mock_drivers()
        return {"items": items, "total": len(items)}
    return {"items": [], "total": 0}


@router.get("/drivers/by-phone/{phone}")
async def get_driver_by_phone(phone: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.YANDEX_MOCK_MODE:
        raise HTTPException(
            status_code=501,
            detail="Поиск водителя по телефону пока доступен только в mock-режиме.",
        )

    driver = get_mock_driver_by_phone(phone)
    if not driver:
        raise HTTPException(status_code=404, detail="Водитель не найден.")
    return driver


@router.get("/drivers/{driver_id}")
async def get_driver(driver_id: str) -> dict[str, Any]:
    settings = get_settings()
    if settings.YANDEX_MOCK_MODE:
        driver = get_mock_driver(driver_id)
        if not driver:
            raise HTTPException(status_code=404, detail="Водитель не найден.")
        return driver

    return {
        "id": driver_id,
        "yandex_driver_id": driver_id,
        "is_enabled": True,
    }


@router.get("/drivers/{driver_id}/filter-settings")
async def get_filter_settings(driver_id: str) -> dict[str, Any]:
    return {"driver_id": driver_id, "enabled": True, "min_price": None}


@router.put("/drivers/{driver_id}/filter-settings")
async def update_filter_settings(
    driver_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {"driver_id": driver_id, "updated": True, "settings": payload}
