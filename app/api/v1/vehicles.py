from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.fleet import FleetProviderError, get_fleet_provider

router = APIRouter(prefix="/api/v1", tags=["vehicles"])


def _provider_error(exc: FleetProviderError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/vehicles")
async def list_vehicles() -> dict[str, Any]:
    try:
        items = await get_fleet_provider().list_vehicles()
    except FleetProviderError as exc:
        raise _provider_error(exc) from exc
    return {"items": items, "total": len(items)}


@router.get("/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str) -> dict[str, Any]:
    try:
        vehicle = await get_fleet_provider().get_vehicle(vehicle_id)
    except FleetProviderError as exc:
        raise _provider_error(exc) from exc
    if not vehicle:
        raise HTTPException(status_code=404, detail="Автомобиль не найден.")
    return vehicle
