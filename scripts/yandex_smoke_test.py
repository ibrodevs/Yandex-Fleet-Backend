from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.core.exceptions import YandexApiError, YandexAuthError, YandexRateLimitError
from app.services.yandex.client import YandexFleetClient


async def run() -> int:
    settings = get_settings()
    if not settings.is_yandex_configured:
        print("AUTH: NOT CONFIGURED")
        return 2

    client = YandexFleetClient(settings=settings)
    try:
        try:
            drivers = await client.list_driver_profiles()
        except YandexAuthError:
            print("AUTH: FAILED")
            print("PARK: UNAVAILABLE")
            return 3
        except (YandexApiError, YandexRateLimitError):
            print("AUTH: UNKNOWN")
            print("PARK: API UNAVAILABLE")
            return 4

        print("AUTH: OK")
        print("PARK: OK")
        print(f"DRIVERS: {len(drivers)}")

        try:
            cars = await client.list_cars()
            print(f"CARS: {len(cars)}")
        except (YandexApiError, YandexAuthError, YandexRateLimitError):
            print("CARS: UNAVAILABLE")

        now = datetime.now(UTC)
        start = now - timedelta(days=max(1, settings.YANDEX_ORDERS_LOOKBACK_DAYS))
        try:
            orders = await client.list_orders(
                booked_from=start.isoformat(),
                booked_to=now.isoformat(),
            )
            print(f"ORDERS: {len(orders)}")
        except (YandexApiError, YandexAuthError, YandexRateLimitError):
            print("ORDERS: UNAVAILABLE")
        return 0
    finally:
        await client.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
