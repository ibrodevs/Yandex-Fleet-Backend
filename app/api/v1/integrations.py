from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/api/v1", tags=["integrations"])


@router.get("/integrations/yandex/status")
async def yandex_status() -> dict:
    settings = get_settings()
    configured = settings.is_yandex_configured
    mock_mode = settings.YANDEX_MOCK_MODE

    return {
        "mode": "mock" if mock_mode else "yandex",
        "configured": configured,
        "fleet_api_available": False if mock_mode else configured,
        "park_id_configured": bool(settings.YANDEX_PARK_ID),
        "last_successful_sync": None,
        "last_sync_error": None,
        "features": {
            "orders_read": mock_mode,
            "drivers_read": mock_mode,
            "vehicles_read": mock_mode,
            "driver_phone_lookup": mock_mode,
            "telegram_bot": True,
            "persistent_telegram_link": True,
            "mock_order_completion": mock_mode,
            "real_order_completion": False,
            "incoming_offers": False,
            "accept_offer": False,
            "reject_offer": False,
            "neutral_skip": False,
        },
    }
