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
)
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
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or YandexFleetClient(settings=self.settings)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _translate(self, awaitable: Any) -> Any:
        try:
            return await awaitable
        except YandexAuthError as exc:
            raise FleetProviderError(
                "Доступ к Yandex Fleet отклонён. Проверьте ключи и доступ к парку."
            ) from exc
        except YandexRateLimitError as exc:
            raise FleetProviderError(
                "Yandex Fleet временно ограничил частоту запросов. Попробуйте позже."
            ) from exc
        except YandexApiError as exc:
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

    async def list_drivers(self) -> list[dict[str, Any]]:
        profiles = await self._translate(self.client.list_driver_profiles())
        result = [
            map_yandex_driver(
                profile,
                default_country_code=self.settings.PHONE_DEFAULT_COUNTRY_CODE,
            )
            for profile in profiles
        ]
        return [driver for driver in result if driver.get("id")]

    async def get_driver(self, driver_id: str) -> dict[str, Any] | None:
        profiles = await self._translate(
            self.client.list_driver_profiles(
                driver_profile_ids=[driver_id],
                max_records=1,
            )
        )
        for profile in profiles:
            driver = map_yandex_driver(
                profile,
                default_country_code=self.settings.PHONE_DEFAULT_COUNTRY_CODE,
            )
            if str(driver.get("id")) == str(driver_id):
                return driver
        return None

    async def get_driver_by_phone(self, phone: str) -> dict[str, Any] | None:
        target = normalize_phone(
            phone,
            default_country_code=self.settings.PHONE_DEFAULT_COUNTRY_CODE,
        )
        if not target:
            return None
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

    async def list_orders(
        self,
        *,
        driver_id: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
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
            orders = [
                order
                for order in orders
                if str(order.get("driver_id")) == str(driver_id)
            ]
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
