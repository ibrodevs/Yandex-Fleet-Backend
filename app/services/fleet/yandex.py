from __future__ import annotations

from typing import Any

from app.services.fleet.base import FleetProvider, FleetProviderError


class YandexFleetProvider(FleetProvider):
    """Adapter boundary for real Fleet data.

    Stage 1 intentionally does not fake real-mode behaviour. Once park
    credentials are available, only this provider needs to be implemented;
    Telegram handlers and public backend contracts stay unchanged.
    """

    def _not_ready(self) -> FleetProviderError:
        return FleetProviderError(
            "Реальный Yandex Fleet provider ещё не активирован. "
            "Добавьте ключи парка и реализуйте mapping ответов Fleet API."
        )

    async def list_drivers(self) -> list[dict[str, Any]]:
        raise self._not_ready()

    async def get_driver(self, driver_id: str) -> dict[str, Any] | None:
        raise self._not_ready()

    async def get_driver_by_phone(self, phone: str) -> dict[str, Any] | None:
        raise self._not_ready()

    async def get_driver_summary(self, driver_id: str) -> dict[str, Any] | None:
        raise self._not_ready()

    async def list_orders(
        self,
        *,
        driver_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        raise self._not_ready()

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        raise self._not_ready()

    async def complete_order(self, order_id: str) -> dict[str, Any]:
        raise FleetProviderError(
            "Завершение реального заказа через публичный Fleet API не поддерживается."
        )
