from __future__ import annotations

from typing import Any

from app import mock_data
from app.services.fleet.base import FleetProvider, FleetProviderError


class MockFleetProvider(FleetProvider):
    async def list_drivers(self) -> list[dict[str, Any]]:
        return mock_data.list_drivers()

    async def get_driver(self, driver_id: str) -> dict[str, Any] | None:
        return mock_data.get_driver(driver_id)

    async def get_driver_by_phone(self, phone: str) -> dict[str, Any] | None:
        return mock_data.get_driver_by_phone(phone)

    async def get_driver_summary(self, driver_id: str) -> dict[str, Any] | None:
        return mock_data.get_driver_summary(driver_id)

    async def list_orders(
        self,
        *,
        driver_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return mock_data.list_orders(driver_id=driver_id, status=status)

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        return mock_data.get_order(order_id)

    async def complete_order(self, order_id: str) -> dict[str, Any]:
        try:
            order = mock_data.complete_order(order_id)
        except ValueError as exc:
            raise FleetProviderError(str(exc)) from exc
        if not order:
            raise FleetProviderError("Заказ не найден.")
        return order
