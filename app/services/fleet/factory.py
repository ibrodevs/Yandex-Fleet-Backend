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


async def close_fleet_provider() -> None:
    if get_fleet_provider.cache_info().currsize == 0:
        return
    provider = get_fleet_provider()
    close = getattr(provider, "aclose", None)
    if close is not None:
        await close()
    get_fleet_provider.cache_clear()
