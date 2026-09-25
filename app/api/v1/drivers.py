from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.fleet import FleetProviderError, get_fleet_provider

router = APIRouter(prefix="/api/v1", tags=["drivers"])


def _provider_error(exc: FleetProviderError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/drivers")
async def list_drivers() -> dict[str, Any]:
    try:
        items = await get_fleet_provider().list_drivers()
    except FleetProviderError as exc:
        raise _provider_error(exc) from exc
    return {"items": items, "total": len(items)}


@router.get("/drivers/by-phone/{phone}")
async def get_driver_by_phone(phone: str) -> dict[str, Any]:
    try:
        driver = await get_fleet_provider().get_driver_by_phone(phone)
    except FleetProviderError as exc:
        raise _provider_error(exc) from exc
    if not driver:
        raise HTTPException(status_code=404, detail="Водитель не найден.")
    return driver


@router.get("/drivers/{driver_id}/summary")
async def get_driver_summary(driver_id: str) -> dict[str, Any]:
    try:
        summary = await get_fleet_provider().get_driver_summary(driver_id)
    except FleetProviderError as exc:
        raise _provider_error(exc) from exc
    if not summary:
        raise HTTPException(status_code=404, detail="Водитель не найден.")
    return summary


@router.get("/drivers/{driver_id}")
async def get_driver(driver_id: str) -> dict[str, Any]:
    try:
        driver = await get_fleet_provider().get_driver(driver_id)
    except FleetProviderError as exc:
        raise _provider_error(exc) from exc
    if not driver:
        raise HTTPException(status_code=404, detail="Водитель не найден.")
    return driver


@router.get("/drivers/{driver_id}/filter-settings")
async def get_filter_settings(driver_id: str) -> dict[str, Any]:
    return {"driver_id": driver_id, "enabled": True, "min_price": None}


@router.put("/drivers/{driver_id}/filter-settings")
async def update_filter_settings(
    driver_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {"driver_id": driver_id, "updated": True, "settings": payload}
