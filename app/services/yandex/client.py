from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import get_settings
from app.core.exceptions import YandexApiError, YandexAuthError, YandexRateLimitError
from app.core.logging import get_logger

logger = get_logger(__name__)


class YandexFleetClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.settings = get_settings()
        self._client = client

    async def _request(self, method: str, url: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Client-ID": self.settings.YANDEX_CLIENT_ID or "",
            "X-API-Key": self.settings.YANDEX_API_KEY or "",
        }

        if not self.settings.YANDEX_CLIENT_ID or not self.settings.YANDEX_API_KEY:
            raise YandexAuthError("Yandex credentials are not configured.")

        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            for attempt in range(1, 4):
                try:
                    response = await client.request(method, url, json=json)
                    if response.status_code == 401:
                        raise YandexAuthError("Yandex Fleet API authentication failed.")
                    if response.status_code == 429:
                        if attempt < 3:
                            await asyncio.sleep(2**attempt)
                            continue
                        raise YandexRateLimitError()
                    if response.status_code >= 400:
                        raise YandexApiError(
                            f"Yandex Fleet API returned status {response.status_code}",
                            status_code=response.status_code,
                            details=response.text,
                        )
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise YandexApiError("Yandex Fleet API returned invalid JSON", details=str(exc)) from exc
                    return payload
                except (httpx.TimeoutException, httpx.HTTPError) as exc:
                    if attempt == 3:
                        raise YandexApiError("Failed to request Yandex Fleet API", details=str(exc)) from exc
                    await asyncio.sleep(2**attempt)

        raise YandexApiError("Failed to request Yandex Fleet API")

    async def get_orders(self, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.settings.YANDEX_FLEET_BASE_URL}/orders/list"
        return await self._request("POST", url, json={"park_id": self.settings.YANDEX_PARK_ID, **kwargs})

    async def get_drivers(self, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.settings.YANDEX_FLEET_BASE_URL}/drivers/list"
        return await self._request("POST", url, json={"park_id": self.settings.YANDEX_PARK_ID, **kwargs})

    async def get_vehicles(self, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.settings.YANDEX_FLEET_BASE_URL}/vehicles/list"
        return await self._request("POST", url, json={"park_id": self.settings.YANDEX_PARK_ID, **kwargs})

    async def get_order_track(self, order_id: str) -> dict[str, Any]:
        url = f"{self.settings.YANDEX_FLEET_BASE_URL}/orders/{order_id}/track"
        return await self._request("GET", url)
