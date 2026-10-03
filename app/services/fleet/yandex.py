from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import Settings, get_settings
from app.core.exceptions import YandexApiError, YandexAuthError, YandexRateLimitError
from app.core.logging import get_logger, log_event
from app.services.fleet.base import FleetProvider, FleetProviderError
from app.services.fleet.phone import normalize_phone
from app.services.fleet.yandex_mappers import (
    map_yandex_driver,
    map_yandex_driver_summary,
    map_yandex_order,
    map_yandex_vehicle,
)
from app.services.yandex.cache import SharedYandexCache
from app.services.yandex.client import YandexFleetClient

logger = get_logger(__name__)

INTERNAL_TO_YANDEX_STATUSES = {
    "assigned": ["driving"],
    "waiting": ["waiting"],
    "in_progress": ["transporting"],
    "completed": ["complete"],
    "cancelled": ["cancelled", "calling", "expired", "failed"],
}


class YandexFleetProvider(FleetProvider):
    supports_order_completion = False

    def __init__(
        self,
        client: YandexFleetClient | None = None,
        *,
        settings: Settings | None = None,
        cache: SharedYandexCache | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or YandexFleetClient(settings=self.settings)
        self.cache = cache or SharedYandexCache(self.settings.YANDEX_CACHE_DB_PATH)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _translate(self, awaitable: Any) -> Any:
        try:
            return await awaitable
        except YandexAuthError as exc:
            log_event(
                logger,
                "yandex_provider_error",
                level="error",
                error_type=type(exc).__name__,
                status_code=exc.status_code,
            )
            raise FleetProviderError(
                "Доступ к Yandex Fleet отклонён. Проверьте ключи и доступ к парку."
            ) from exc
        except YandexRateLimitError as exc:
            log_event(
                logger,
                "yandex_provider_error",
                level="error",
                error_type=type(exc).__name__,
                status_code=exc.status_code,
            )
            raise FleetProviderError(
                "Yandex Fleet временно ограничил частоту запросов. Попробуйте позже."
            ) from exc
        except YandexApiError as exc:
            log_event(
                logger,
                "yandex_provider_error",
                level="error",
                error_type=type(exc).__name__,
                status_code=exc.status_code,
            )
            if exc.status_code == 504:
                message = "Данные Яндекс временно недоступны: превышено время ожидания."
            else:
                message = "Данные Яндекс временно недоступны. Попробуйте обновить позже."
            raise FleetProviderError(message) from exc

    def _date_range(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> tuple[str, str]:
        now = datetime.now(UTC)
        start = now - timedelta(days=max(1, self.settings.YANDEX_ORDERS_LOOKBACK_DAYS))
        return date_from or start.isoformat(), date_to or now.isoformat()

    async def _driver_profiles_snapshot(self) -> list[dict[str, Any]]:
        async def stale_refresh() -> list[dict[str, Any]]:
            return await self.client.list_driver_profiles(retry_safe=False)

        return await self._translate(
            self.cache.get_or_refresh(
                "drivers:park:default",
                ttl_seconds=self.settings.YANDEX_DRIVER_CACHE_TTL_SECONDS,
                stale_seconds=self.settings.YANDEX_CACHE_STALE_SECONDS,
                refresh=self.client.list_driver_profiles,
                stale_refresh=stale_refresh,
            )
        )

    async def _park_orders_snapshot(self) -> list[dict[str, Any]]:
        async def refresh(*, retry_safe: bool = True) -> list[dict[str, Any]]:
            booked_from, booked_to = self._date_range()
            return await self.client.list_orders(
                booked_from=booked_from,
                booked_to=booked_to,
                retry_safe=retry_safe,
            )

        return await self._translate(
            self.cache.get_or_refresh(
                "orders:park:default",
                ttl_seconds=self.settings.YANDEX_ORDERS_CACHE_TTL_SECONDS,
                stale_seconds=self.settings.YANDEX_CACHE_STALE_SECONDS,
                refresh=refresh,
                stale_refresh=lambda: refresh(retry_safe=False),
            )
        )

    async def _driver_orders_snapshot(self, driver_id: str) -> list[dict[str, Any]]:
        # The worker may already have a fresh park snapshot. Otherwise query
        # only this driver's orders so a mobile refresh does not paginate the
        # entire park while the phone waits for a response.
        park_entry = await self.cache.get("orders:park:default")
        park_age = (
            max(0.0, self.cache.clock() - park_entry.updated_at)
            if park_entry and isinstance(park_entry.payload, list)
            else None
        )

        def park_driver_orders() -> list[dict[str, Any]]:
            assert park_entry is not None
            return [
                order
                for order in park_entry.payload
                if str((order.get("driver_profile") or {}).get("id")) == driver_id
            ]

        if park_age is not None and park_age <= self.settings.YANDEX_ORDERS_CACHE_TTL_SECONDS:
            return park_driver_orders()

        async def refresh() -> list[dict[str, Any]]:
            booked_from, booked_to = self._date_range()
            return await self.client.list_orders(
                booked_from=booked_from,
                booked_to=booked_to,
                driver_profile_id=driver_id,
                retry_safe=False,
            )

        async def snapshot() -> list[dict[str, Any]]:
            try:
                return await self.cache.get_or_refresh(
                    f"orders:driver:{driver_id}",
                    ttl_seconds=self.settings.YANDEX_ORDERS_CACHE_TTL_SECONDS,
                    stale_seconds=self.settings.YANDEX_CACHE_STALE_SECONDS,
                    refresh=refresh,
                )
            except (YandexApiError, YandexRateLimitError) as exc:
                # Preserve the former park-wide stale fallback when the exact
                # driver query hits a temporary upstream failure.
                temporary = isinstance(exc, YandexRateLimitError) or exc.status_code >= 500
                if (
                    temporary
                    and park_age is not None
                    and park_age
                    <= self.settings.YANDEX_ORDERS_CACHE_TTL_SECONDS
                    + self.settings.YANDEX_CACHE_STALE_SECONDS
                ):
                    return park_driver_orders()
                raise

        return await self._translate(snapshot())

    async def list_drivers(self) -> list[dict[str, Any]]:
        profiles = await self._driver_profiles_snapshot()
        result = [
            map_yandex_driver(
                profile,
                default_country_code=self.settings.PHONE_DEFAULT_COUNTRY_CODE,
            )
            for profile in profiles
        ]
        return [driver for driver in result if driver.get("id")]

    async def get_driver(self, driver_id: str) -> dict[str, Any] | None:
        driver_id = str(driver_id)
        # Reuse a fresh park snapshot when the worker has already loaded it.
        # A cold mobile request only needs one exact driver profile.
        park_entry = await self.cache.get("drivers:park:default")
        park_age = (
            max(0.0, self.cache.clock() - park_entry.updated_at)
            if park_entry and isinstance(park_entry.payload, list)
            else None
        )
        if park_age is not None and park_age <= self.settings.YANDEX_DRIVER_CACHE_TTL_SECONDS:
            profiles = park_entry.payload
        else:

            async def refresh() -> list[dict[str, Any]]:
                return await self.client.list_driver_profiles(
                    driver_profile_ids=[driver_id], max_records=1, retry_safe=False
                )

            async def snapshot() -> list[dict[str, Any]]:
                try:
                    return await self.cache.get_or_refresh(
                        f"drivers:profile:{driver_id}",
                        ttl_seconds=self.settings.YANDEX_DRIVER_CACHE_TTL_SECONDS,
                        stale_seconds=self.settings.YANDEX_CACHE_STALE_SECONDS,
                        refresh=refresh,
                    )
                except (YandexApiError, YandexRateLimitError) as exc:
                    temporary = isinstance(exc, YandexRateLimitError) or exc.status_code >= 500
                    if (
                        temporary
                        and park_age is not None
                        and park_age
                        <= self.settings.YANDEX_DRIVER_CACHE_TTL_SECONDS
                        + self.settings.YANDEX_CACHE_STALE_SECONDS
                    ):
                        return park_entry.payload
                    raise

            profiles = await self._translate(snapshot())
        for profile in profiles:
            driver = map_yandex_driver(
                profile,
                default_country_code=self.settings.PHONE_DEFAULT_COUNTRY_CODE,
            )
            if driver.get("id") == driver_id:
                return driver
        return None

    async def get_driver_by_phone(self, phone: str) -> dict[str, Any] | None:
        target = normalize_phone(
            phone,
            default_country_code=self.settings.PHONE_DEFAULT_COUNTRY_CODE,
        )
        if not target:
            return None

        def match(profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
            for profile in profiles:
                driver = map_yandex_driver(
                    profile,
                    default_country_code=self.settings.PHONE_DEFAULT_COUNTRY_CODE,
                )
                if driver.get("id") and target in set(driver.get("phones") or []):
                    return driver
            return None

        # Preserve the existing shared snapshot fast path while it is fresh.
        entry = await self.cache.get("drivers:park:default")
        if (
            entry
            and isinstance(entry.payload, list)
            and (
                max(0.0, self.cache.clock() - entry.updated_at)
                <= self.settings.YANDEX_DRIVER_CACHE_TTL_SECONDS
            )
        ):
            return match(entry.payload)

        # Yandex's documented text query accepts a phone and avoids waiting for
        # every page of the park-wide snapshot during login. Verify the exact
        # normalized phone before authorizing; search results alone are not proof.
        profiles = await self._translate(
            self.client.list_driver_profiles(search_text=target, max_records=100, retry_safe=False)
        )
        found = match(profiles)
        if found:
            return found
        # Keep the original full lookup for parks where text search does not
        # return a phone or the number is absent.
        for driver in await self.list_drivers():
            if target in set(driver.get("phones") or []):
                return driver
        return None

    async def get_driver_summary(self, driver_id: str) -> dict[str, Any] | None:
        driver = await self.get_driver(driver_id)
        if not driver:
            return None
        orders = await self.list_orders(driver_id=driver_id)
        return map_yandex_driver_summary(
            driver_id,
            orders,
            currency=driver.get("currency"),
        )

    async def list_vehicles(self) -> list[dict[str, Any]]:
        cars = await self._translate(self.client.list_cars())
        return [vehicle for raw in cars if (vehicle := map_yandex_vehicle(raw))]

    async def get_vehicle(self, vehicle_id: str) -> dict[str, Any] | None:
        cars = await self._translate(self.client.list_cars(car_ids=[vehicle_id], max_records=1))
        for raw in cars:
            vehicle = map_yandex_vehicle(raw)
            if vehicle and str(vehicle.get("id")) == str(vehicle_id):
                return vehicle
        return None

    async def list_orders(
        self,
        *,
        driver_id: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        if status is None and date_from is None and date_to is None:
            raw_orders = (
                await self._driver_orders_snapshot(str(driver_id))
                if driver_id
                else await self._park_orders_snapshot()
            )
        else:
            booked_from, booked_to = self._date_range(date_from, date_to)
            statuses = INTERNAL_TO_YANDEX_STATUSES.get(status) if status else None
            raw_orders = await self._translate(
                self.client.list_orders(
                    booked_from=booked_from,
                    booked_to=booked_to,
                    driver_profile_id=driver_id,
                    statuses=statuses,
                )
            )
        orders = [map_yandex_order(raw) for raw in raw_orders]
        if driver_id:
            orders = [order for order in orders if str(order.get("driver_id")) == str(driver_id)]
        if status:
            orders = [order for order in orders if order.get("status") == status]
        orders.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return orders

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        booked_from, booked_to = self._date_range()
        raw_orders = await self._translate(
            self.client.list_orders(
                booked_from=booked_from,
                booked_to=booked_to,
                order_ids=[order_id],
                max_records=1,
            )
        )
        raw = next(
            (item for item in raw_orders if str(item.get("id")) == str(order_id)),
            None,
        )
        if not raw:
            return None
        order = map_yandex_order(raw)
        try:
            track = await self.client.get_order_track(order_id)
        except (YandexApiError, YandexAuthError, YandexRateLimitError) as exc:
            log_event(
                logger,
                "yandex_order_track_unavailable",
                level="warning",
                order_id=order_id,
                error_type=type(exc).__name__,
            )
        else:
            order["track"] = track.get("track") if isinstance(track, dict) else None
        return order

    async def complete_order(self, order_id: str) -> dict[str, Any]:
        raise FleetProviderError(
            "Завершение реального заказа через публичный Yandex Fleet API "
            "не поддерживается. Завершите поездку в Яндекс Про."
        )
