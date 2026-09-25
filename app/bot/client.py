from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx


class BackendError(RuntimeError):
    pass


class BackendClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise BackendError(f"Backend недоступен: {exc}") from exc

        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            try:
                payload = response.json()
                detail = payload.get("detail", payload)
            except ValueError:
                detail = response.text[:300]
            raise BackendError(f"HTTP {response.status_code}: {detail}")

        if not response.content:
            return None
        return response.json()

    async def get_driver_by_phone(self, phone: str) -> dict[str, Any] | None:
        encoded_phone = quote(phone, safe="")
        return await self._request(
            "GET",
            f"/api/v1/drivers/by-phone/{encoded_phone}",
        )

    async def get_driver(self, driver_id: str) -> dict[str, Any] | None:
        data = await self._request("GET", f"/api/v1/drivers/{driver_id}")
        return data if isinstance(data, dict) else None

    async def get_driver_summary(self, driver_id: str) -> dict[str, Any] | None:
        data = await self._request(
            "GET",
            f"/api/v1/drivers/{driver_id}/summary",
        )
        return data if isinstance(data, dict) else None

    async def list_orders(
        self,
        driver_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        params: dict[str, Any] = {
            "driver_id": driver_id,
            "limit": limit,
            "offset": offset,
        }
        if status:
            params["status"] = status

        data = await self._request(
            "GET",
            "/api/v1/orders",
            params=params,
        )
        if not isinstance(data, dict):
            return [], 0

        items = data.get("items", [])
        total = data.get("total", 0)
        return (
            items if isinstance(items, list) else [],
            int(total) if isinstance(total, int) else 0,
        )

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        data = await self._request("GET", f"/api/v1/orders/{order_id}")
        if not isinstance(data, dict):
            return None
        order = data.get("order")
        return order if isinstance(order, dict) else None

    async def complete_order(self, order_id: str) -> dict[str, Any]:
        data = await self._request(
            "POST",
            f"/api/v1/orders/{order_id}/complete",
        )
        if not isinstance(data, dict):
            raise BackendError("Backend вернул некорректный ответ.")
        order = data.get("order")
        if not isinstance(order, dict):
            raise BackendError("В ответе backend отсутствует заказ.")
        return order
