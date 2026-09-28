from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.core.exceptions import YandexApiError, YandexAuthError, YandexRateLimitError
from app.core.logging import get_logger, log_event

logger = get_logger(__name__)

DRIVER_PROFILES_PATH = "/v1/parks/driver-profiles/list"
CARS_PATH = "/v1/parks/cars/list"
ORDERS_PATH = "/v1/parks/orders/list"
ORDER_TRACK_PATH = "/v1/parks/orders/track"


class YandexFleetClient:
    """Read-only client for the documented public Yandex Fleet API."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        settings: Settings | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self._owns_client = client is None
        self._sleep = sleep
        self._jitter = jitter
        self._wall_clock = wall_clock

    def _headers(self) -> dict[str, str]:
        if not self.settings.YANDEX_CLIENT_ID or not self.settings.YANDEX_API_KEY:
            raise YandexAuthError("Yandex Fleet credentials are not configured.")
        return {
            "Accept-Language": "ru",
            "Content-Type": "application/json",
            "X-Client-ID": self.settings.YANDEX_CLIENT_ID,
            "X-API-Key": self.settings.YANDEX_API_KEY,
        }

    def _park_id(self) -> str:
        if not self.settings.YANDEX_PARK_ID:
            raise YandexAuthError("Yandex park id is not configured.")
        return self.settings.YANDEX_PARK_ID

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                self.settings.YANDEX_HTTP_READ_TIMEOUT_SECONDS,
                connect=self.settings.YANDEX_HTTP_CONNECT_TIMEOUT_SECONDS,
            )
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None

    @staticmethod
    def _error_details(response: httpx.Response) -> dict[str, Any]:
        details: dict[str, Any] = {"upstream_status": response.status_code}
        try:
            payload = response.json()
        except ValueError:
            text = response.text.strip()
            if text:
                details["upstream_message"] = text[:500]
            return details
        if isinstance(payload, dict):
            if payload.get("code"):
                details["upstream_code"] = str(payload["code"])
            if payload.get("message"):
                details["upstream_message"] = str(payload["message"])[:500]
        return details

    def _retry_delay(
        self,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> float:
        delay: float | None = None
        retry_after = response.headers.get("Retry-After") if response is not None else None
        if retry_after:
            try:
                delay = max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    delay = max(
                        0.0,
                        retry_at.timestamp() - datetime.fromtimestamp(
                            self._wall_clock(),
                            tz=UTC,
                        ).timestamp(),
                    )
                except (TypeError, ValueError, OverflowError):
                    delay = None
        if delay is None:
            delay = float(2 ** (attempt - 1))
        return delay + self._jitter(0.1, 0.5)

    async def _retry_wait(
        self,
        *,
        path: str,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> None:
        delay = self._retry_delay(attempt, response)
        log_event(
            logger,
            "yandex_retry_scheduled",
            endpoint=path,
            attempt=attempt,
            status_code=response.status_code if response is not None else None,
            delay_seconds=round(delay, 3),
        )
        await self._sleep(delay)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retry_safe: bool = True,
    ) -> dict[str, Any]:
        attempts = max(1, min(self.settings.YANDEX_RETRY_ATTEMPTS, 5))
        url = f"{self.settings.YANDEX_FLEET_BASE_URL.rstrip('/')}{path}"

        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                response = await self._http_client().request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json,
                    params=params,
                )
            except httpx.TimeoutException as exc:
                log_event(
                    logger,
                    "yandex_request_timeout",
                    level="warning",
                    endpoint=path,
                    attempt=attempt,
                    duration_ms=round((time.monotonic() - started) * 1000),
                )
                if retry_safe and attempt < attempts:
                    await self._retry_wait(path=path, attempt=attempt)
                    continue
                raise YandexApiError(
                    "Yandex Fleet API request timed out.",
                    status_code=504,
                    details={"endpoint": path},
                ) from exc
            except httpx.HTTPError as exc:
                log_event(
                    logger,
                    "yandex_network_error",
                    level="warning",
                    endpoint=path,
                    attempt=attempt,
                    error_type=type(exc).__name__,
                )
                if retry_safe and attempt < attempts:
                    await self._retry_wait(path=path, attempt=attempt)
                    continue
                raise YandexApiError(
                    "Yandex Fleet API network error.",
                    status_code=502,
                    details={"endpoint": path, "error_type": type(exc).__name__},
                ) from exc

            duration_ms = round((time.monotonic() - started) * 1000)
            log_event(
                logger,
                "yandex_request",
                endpoint=path,
                status_code=response.status_code,
                attempt=attempt,
                duration_ms=duration_ms,
            )

            if response.status_code in {401, 403}:
                raise YandexAuthError(
                    "Yandex Fleet API rejected the credentials or park access.",
                    status_code=response.status_code,
                    details=self._error_details(response),
                )
            if response.status_code == 429:
                if retry_safe and attempt < attempts:
                    await self._retry_wait(
                        path=path,
                        attempt=attempt,
                        response=response,
                    )
                    continue
                raise YandexRateLimitError(details=self._error_details(response))
            if response.status_code >= 500 and retry_safe and attempt < attempts:
                await self._retry_wait(
                    path=path,
                    attempt=attempt,
                    response=response,
                )
                continue
            if response.status_code >= 400:
                raise YandexApiError(
                    f"Yandex Fleet API returned HTTP {response.status_code}.",
                    status_code=response.status_code,
                    details=self._error_details(response),
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise YandexApiError(
                    "Yandex Fleet API returned invalid JSON.",
                    status_code=502,
                    details={"endpoint": path},
                ) from exc
            if not isinstance(payload, dict):
                raise YandexApiError(
                    "Yandex Fleet API returned an unexpected response.",
                    status_code=502,
                    details={"endpoint": path},
                )
            return payload

        raise YandexApiError("Yandex Fleet API request failed.")

    def _limits(self, requested: int | None, endpoint_max: int) -> tuple[int, int, int]:
        max_records = max(1, self.settings.YANDEX_MAX_RECORDS)
        if requested is not None:
            max_records = min(max_records, max(1, requested))
        page_size = min(endpoint_max, max_records)
        max_pages = max(1, self.settings.YANDEX_MAX_PAGES)
        return page_size, max_pages, max_records

    async def list_driver_profiles(
        self,
        *,
        driver_profile_ids: list[str] | None = None,
        max_records: int | None = None,
    ) -> list[dict[str, Any]]:
        page_size, max_pages, record_limit = self._limits(max_records, 1000)
        offset = 0
        result: list[dict[str, Any]] = []

        for _ in range(max_pages):
            park: dict[str, Any] = {"id": self._park_id()}
            if driver_profile_ids:
                park["driver_profile"] = {"id": driver_profile_ids[:100]}
            payload = await self._request(
                "POST",
                DRIVER_PROFILES_PATH,
                json={"query": {"park": park}, "limit": page_size, "offset": offset},
            )
            items = payload.get("driver_profiles") or []
            if not isinstance(items, list):
                raise YandexApiError("Yandex driver profiles response is malformed.")
            result.extend(item for item in items if isinstance(item, dict))
            total = int(payload.get("total") or len(result))
            if not items or len(result) >= total or len(result) >= record_limit:
                break
            next_offset = offset + len(items)
            if next_offset <= offset:
                break
            offset = next_offset

        result = result[:record_limit]
        log_event(logger, "yandex_driver_profiles_loaded", item_count=len(result))
        return result

    async def list_cars(
        self,
        *,
        car_ids: list[str] | None = None,
        max_records: int | None = None,
    ) -> list[dict[str, Any]]:
        page_size, max_pages, record_limit = self._limits(max_records, 1000)
        offset = 0
        result: list[dict[str, Any]] = []

        for _ in range(max_pages):
            park: dict[str, Any] = {"id": self._park_id()}
            if car_ids:
                park["car"] = {"id": car_ids[:100]}
            payload = await self._request(
                "POST",
                CARS_PATH,
                json={"query": {"park": park}, "limit": page_size, "offset": offset},
            )
            items = payload.get("cars") or []
            if not isinstance(items, list):
                raise YandexApiError("Yandex cars response is malformed.")
            result.extend(item for item in items if isinstance(item, dict))
            total = int(payload.get("total") or len(result))
            if not items or len(result) >= total or len(result) >= record_limit:
                break
            next_offset = offset + len(items)
            if next_offset <= offset:
                break
            offset = next_offset

        result = result[:record_limit]
        log_event(logger, "yandex_cars_loaded", item_count=len(result))
        return result

    async def list_orders(
        self,
        *,
        booked_from: str,
        booked_to: str,
        driver_profile_id: str | None = None,
        order_ids: list[str] | None = None,
        statuses: list[str] | None = None,
        max_records: int | None = None,
    ) -> list[dict[str, Any]]:
        page_size, max_pages, record_limit = self._limits(max_records, 500)
        result: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()

        for _ in range(max_pages):
            order_filter: dict[str, Any] = {
                "booked_at": {"from": booked_from, "to": booked_to}
            }
            if order_ids:
                order_filter["ids"] = order_ids[:100]
            if statuses:
                order_filter["statuses"] = statuses
            park: dict[str, Any] = {"id": self._park_id(), "order": order_filter}
            if driver_profile_id:
                park["driver_profile"] = {"id": driver_profile_id}
            body: dict[str, Any] = {"query": {"park": park}, "limit": page_size}
            if cursor:
                body["cursor"] = cursor

            payload = await self._request("POST", ORDERS_PATH, json=body)
            items = payload.get("orders") or []
            if not isinstance(items, list):
                raise YandexApiError("Yandex orders response is malformed.")
            result.extend(item for item in items if isinstance(item, dict))

            next_cursor = payload.get("cursor")
            if (
                not items
                or len(result) >= record_limit
                or not isinstance(next_cursor, str)
                or not next_cursor
                or next_cursor in seen_cursors
            ):
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        result = result[:record_limit]
        log_event(
            logger,
            "yandex_orders_loaded",
            item_count=len(result),
            driver_id=driver_profile_id,
        )
        return result

    async def get_order_track(self, order_id: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            ORDER_TRACK_PATH,
            params={"order_id": order_id, "park_id": self._park_id()},
        )
