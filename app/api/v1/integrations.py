from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import get_settings
from app.core.exceptions import YandexApiError, YandexAuthError, YandexRateLimitError
from app.core.logging import get_logger, log_event
from app.services.yandex.client import YandexFleetClient

router = APIRouter(prefix="/api/v1", tags=["integrations"])
logger = get_logger(__name__)
_last_successful_sync: str | None = None


@router.get("/integrations/yandex/status")
async def yandex_status() -> dict:
    global _last_successful_sync

    settings = get_settings()
    configured = settings.is_yandex_configured
    mock_mode = settings.YANDEX_MOCK_MODE
    park_accessible: bool | None = None
    fleet_api_available: bool | None = None
    last_sync_error: str | None = None

    if not mock_mode and configured:
        client = YandexFleetClient(settings=settings)
        try:
            await client.list_driver_profiles(max_records=1)
            park_accessible = True
            fleet_api_available = True
            _last_successful_sync = datetime.now(UTC).isoformat()
        except YandexAuthError as exc:
            park_accessible = False
            fleet_api_available = True
            last_sync_error = "Yandex rejected credentials or park access."
            log_event(
                logger,
                "yandex_status_check_failed",
                level="error",
                error_type=type(exc).__name__,
                status_code=exc.status_code,
            )
        except (YandexApiError, YandexRateLimitError) as exc:
            park_accessible = None
            fleet_api_available = False
            last_sync_error = "Yandex Fleet API is temporarily unavailable."
            log_event(
                logger,
                "yandex_status_check_failed",
                level="error",
                error_type=type(exc).__name__,
                status_code=exc.status_code,
            )
        finally:
            await client.aclose()
    elif mock_mode:
        fleet_api_available = False
    else:
        fleet_api_available = False
        park_accessible = False
        last_sync_error = "Yandex credentials are not fully configured."

    real_read_ready = not mock_mode and configured and park_accessible is True
    return {
        "mode": "mock" if mock_mode else "yandex",
        "configured": configured,
        "credentials_present": configured,
        "fleet_api_available": fleet_api_available,
        "park_accessible": park_accessible,
        "park_id_configured": bool(settings.YANDEX_PARK_ID),
        "last_successful_sync": _last_successful_sync,
        "last_sync_error": last_sync_error,
        "features": {
            "orders_read": mock_mode or real_read_ready,
            "drivers_read": mock_mode or real_read_ready,
            "vehicles_read": mock_mode or real_read_ready,
            "driver_phone_lookup": True,
            "order_track": not mock_mode and configured,
            "telegram_bot": True,
            "telegram_mini_app": True,
            "multi_source_marketplace_mock": mock_mode,
            "mock_incoming_offers": mock_mode,
            "estimated_price_demo": mock_mode,
            "persistent_telegram_link": True,
            "mock_order_completion": mock_mode,
            "real_order_completion": False,
            "incoming_offers": False,
            "accept_offer": False,
            "reject_offer": False,
            "neutral_skip": False,
        },
    }
