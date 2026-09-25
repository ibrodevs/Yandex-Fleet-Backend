from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FleetProviderError(RuntimeError):
    """Provider-level error that can be translated to an API response."""


class FleetProvider(ABC):
    @abstractmethod
    async def list_drivers(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_driver(self, driver_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def get_driver_by_phone(self, phone: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def get_driver_summary(self, driver_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def list_orders(
        self,
        *,
        driver_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def complete_order(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError
