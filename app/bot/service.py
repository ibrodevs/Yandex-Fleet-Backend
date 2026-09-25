from __future__ import annotations

from typing import Any, Protocol

from app.bot.client import BackendError
from app.services.fleet import FleetProvider, FleetProviderError, get_fleet_provider


class BotBackend(Protocol):
    async def get_driver_by_phone(self, phone: str) -> dict[str, Any] | None: ...
    async def get_driver(self, driver_id: str) -> dict[str, Any] | None: ...
    async def get_driver_summary(self, driver_id: str) -> dict[str, Any] | None: ...
    async def list_orders(
        self,
        driver_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]: ...
    async def get_order(self, order_id: str) -> dict[str, Any] | None: ...
    async def complete_order(self, order_id: str) -> dict[str, Any]: ...


class LocalBackendService:
    """In-process backend adapter for webhook deployments.

    This avoids calling the public backend URL from the web app back into
    itself. The Telegram layer still talks to the same FleetProvider contract
    used by the REST API.
    """

    def __init__(self, provider: FleetProvider | None = None) -> None:
        self.provider = provider or get_fleet_provider()

    def _wrap_error(self, exc: FleetProviderError) -> BackendError:
        return BackendError(str(exc))

    async def get_driver_by_phone(self, phone: str) -> dict[str, Any] | None:
        try:
            return await self.provider.get_driver_by_phone(phone)
        except FleetProviderError as exc:
            raise self._wrap_error(exc) from exc

    async def get_driver(self, driver_id: str) -> dict[str, Any] | None:
        try:
            return await self.provider.get_driver(driver_id)
        except FleetProviderError as exc:
            raise self._wrap_error(exc) from exc

    async def get_driver_summary(self, driver_id: str) -> dict[str, Any] | None:
        try:
            return await self.provider.get_driver_summary(driver_id)
        except FleetProviderError as exc:
            raise self._wrap_error(exc) from exc

    async def list_orders(
        self,
        driver_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        try:
            items = await self.provider.list_orders(
                driver_id=driver_id,
                status=status,
            )
        except FleetProviderError as exc:
            raise self._wrap_error(exc) from exc
        total = len(items)
        return items[offset : offset + limit], total

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        try:
            return await self.provider.get_order(order_id)
        except FleetProviderError as exc:
            raise self._wrap_error(exc) from exc

    async def complete_order(self, order_id: str) -> dict[str, Any]:
        try:
            return await self.provider.complete_order(order_id)
        except FleetProviderError as exc:
            raise self._wrap_error(exc) from exc
