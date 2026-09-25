from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["integrations"])


@router.get("/integrations/yandex/status")
async def yandex_status() -> dict:
    return {
        "configured": False,
        "fleet_api_available": False,
        "park_id_configured": False,
        "last_successful_sync": None,
        "last_sync_error": None,
        "features": {
            "orders_read": False,
            "drivers_read": False,
            "vehicles_read": False,
            "incoming_offers": False,
            "accept_offer": False,
            "reject_offer": False,
            "neutral_skip": False,
        },
    }
