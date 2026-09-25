from functools import lru_cache

from app.config import get_settings
from app.services.fleet.base import FleetProvider
from app.services.fleet.mock import MockFleetProvider
from app.services.fleet.yandex import YandexFleetProvider


@lru_cache
def get_fleet_provider() -> FleetProvider:
    settings = get_settings()
    if settings.YANDEX_MOCK_MODE:
        return MockFleetProvider()
    return YandexFleetProvider()
