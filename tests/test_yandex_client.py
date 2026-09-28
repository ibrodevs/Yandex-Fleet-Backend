import json

import httpx
import pytest

from app.config import Settings
from app.core.exceptions import YandexApiError, YandexAuthError, YandexRateLimitError
from app.services.yandex.client import (
    CARS_PATH,
    DRIVER_PROFILES_PATH,
    ORDER_TRACK_PATH,
    ORDERS_PATH,
    YandexFleetClient,
)


def make_settings(**overrides):
    values = {
        "YANDEX_FLEET_BASE_URL": "https://fleet-api.test",
        "YANDEX_CLIENT_ID": "test-client",
        "YANDEX_API_KEY": "test-key",
        "YANDEX_PARK_ID": "test-park",
        "YANDEX_MAX_PAGES": 5,
        "YANDEX_MAX_RECORDS": 10,
        "YANDEX_RETRY_ATTEMPTS": 2,
    }
    values.update(overrides)
    return Settings(**values)


def response(request: httpx.Request, status: int, payload) -> httpx.Response:
    if isinstance(payload, str):
        return httpx.Response(status, text=payload, request=request)
    return httpx.Response(status, json=payload, request=request)


@pytest.mark.asyncio
async def test_driver_profiles_uses_official_endpoint_headers_and_offset_pagination():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        offset = body["offset"]
        items = [{"driver_profile": {"id": f"driver-{offset + index}"}} for index in range(2)]
        if offset == 2:
            items = [{"driver_profile": {"id": "driver-2"}}]
        return response(
            request,
            200,
            {"driver_profiles": items, "limit": 2, "offset": offset, "total": 3},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(http, settings=make_settings(YANDEX_MAX_RECORDS=3))

    profiles = await client.list_driver_profiles()

    assert [item["driver_profile"]["id"] for item in profiles] == [
        "driver-0",
        "driver-1",
        "driver-2",
    ]
    assert [json.loads(item.content)["offset"] for item in requests] == [0, 2]
    assert requests[0].url.path == DRIVER_PROFILES_PATH
    assert requests[0].headers["X-Client-ID"] == "test-client"
    assert requests[0].headers["X-API-Key"] == "test-key"
    assert json.loads(requests[0].content)["query"]["park"]["id"] == "test-park"
    await http.aclose()


@pytest.mark.asyncio
async def test_cars_uses_official_endpoint_and_offset_pagination():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        offset = body["offset"]
        items = [{"id": f"car-{offset}", "brand": "Toyota"}]
        return response(
            request,
            200,
            {"cars": items, "limit": 1, "offset": offset, "total": 2},
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(http, settings=make_settings(YANDEX_MAX_RECORDS=2))

    cars = await client.list_cars()

    assert [item["id"] for item in cars] == ["car-0", "car-1"]
    assert [json.loads(item.content)["offset"] for item in requests] == [0, 1]
    assert requests[0].url.path == CARS_PATH
    await http.aclose()


@pytest.mark.asyncio
async def test_orders_uses_cursor_filters_and_stops_on_repeated_cursor():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        item_id = "one" if len(bodies) == 1 else "two"
        return response(request, 200, {"orders": [{"id": item_id}], "cursor": "same"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(http, settings=make_settings())

    orders = await client.list_orders(
        booked_from="2026-09-20T00:00:00+00:00",
        booked_to="2026-09-27T00:00:00+00:00",
        driver_profile_id="driver-1",
        order_ids=["order-1"],
        statuses=["complete"],
    )

    assert [item["id"] for item in orders] == ["one", "two"]
    assert len(bodies) == 2
    assert "cursor" not in bodies[0]
    assert bodies[1]["cursor"] == "same"
    park = bodies[0]["query"]["park"]
    assert park["driver_profile"]["id"] == "driver-1"
    assert park["order"]["ids"] == ["order-1"]
    assert park["order"]["statuses"] == ["complete"]
    assert park["order"]["booked_at"]["from"].startswith("2026-09-20")
    await http.aclose()


@pytest.mark.asyncio
async def test_order_track_uses_query_parameters():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return response(request, 200, {"track": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(http, settings=make_settings())
    assert await client.get_order_track("order-1") == {"track": []}
    assert captured[0].url.path == ORDER_TRACK_PATH
    assert captured[0].url.params["order_id"] == "order-1"
    assert captured[0].url.params["park_id"] == "test-park"
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 404, 409])
async def test_client_preserves_non_retryable_http_errors(status: int):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response(request, status, {"code": "bad_request", "message": "Rejected"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(http, settings=make_settings())
    with pytest.raises(YandexApiError) as error:
        await client.list_driver_profiles()
    assert error.value.status_code == status
    assert calls == 1
    await http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_client_distinguishes_auth_errors(status: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return response(request, status, {"message": "Denied"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(http, settings=make_settings())
    with pytest.raises(YandexAuthError) as error:
        await client.list_driver_profiles()
    assert error.value.status_code == status
    await http.aclose()


@pytest.mark.asyncio
async def test_client_retries_rate_limit_then_fails():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response(request, 429, {"message": "Slow down"})

    async def no_sleep(_: float) -> None:
        return None

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(http, settings=make_settings(), sleep=no_sleep)
    with pytest.raises(YandexRateLimitError):
        await client.list_driver_profiles()
    assert calls == 2
    await http.aclose()


@pytest.mark.asyncio
async def test_client_honors_retry_after_seconds_with_jitter():
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                json={"message": "Slow down"},
                headers={"Retry-After": "2"},
                request=request,
            )
        return response(request, 200, {"driver_profiles": [], "total": 0})

    async def capture_sleep(delay: float) -> None:
        sleeps.append(delay)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(
        http,
        settings=make_settings(),
        sleep=capture_sleep,
        jitter=lambda _start, _end: 0.2,
    )

    assert await client.list_driver_profiles() == []
    assert sleeps == [2.2]
    await http.aclose()


@pytest.mark.asyncio
async def test_client_honors_retry_after_http_date_with_jitter():
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                json={"message": "Slow down"},
                headers={"Retry-After": "Thu, 01 Jan 1970 00:16:42 GMT"},
                request=request,
            )
        return response(request, 200, {"driver_profiles": [], "total": 0})

    async def capture_sleep(delay: float) -> None:
        sleeps.append(delay)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(
        http,
        settings=make_settings(),
        sleep=capture_sleep,
        jitter=lambda _start, _end: 0.25,
        wall_clock=lambda: 1000.0,
    )

    assert await client.list_driver_profiles() == []
    assert sleeps == [2.25]
    await http.aclose()


@pytest.mark.asyncio
async def test_client_uses_exponential_fallback_without_retry_after():
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return response(request, 429, {"message": "Slow down"})
        return response(request, 200, {"driver_profiles": [], "total": 0})

    async def capture_sleep(delay: float) -> None:
        sleeps.append(delay)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(
        http,
        settings=make_settings(),
        sleep=capture_sleep,
        jitter=lambda _start, _end: 0.3,
    )

    assert await client.list_driver_profiles() == []
    assert sleeps == [1.3]
    await http.aclose()


@pytest.mark.asyncio
async def test_client_retries_server_error_and_handles_invalid_json():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return response(request, 500, {"message": "Temporary"})
        return response(request, 200, "not-json")

    async def no_sleep(_: float) -> None:
        return None

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(http, settings=make_settings(), sleep=no_sleep)
    with pytest.raises(YandexApiError, match="invalid JSON"):
        await client.list_driver_profiles()
    assert calls == 2
    await http.aclose()


@pytest.mark.asyncio
async def test_client_retries_timeout_without_leaking_credentials():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout", request=request)

    async def no_sleep(_: float) -> None:
        return None

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(http, settings=make_settings(), sleep=no_sleep)
    with pytest.raises(YandexApiError) as error:
        await client.list_driver_profiles()
    assert error.value.status_code == 504
    assert "test-key" not in str(error.value)
    assert calls == 2
    await http.aclose()


def test_official_orders_endpoint_constant():
    assert ORDERS_PATH == "/v1/parks/orders/list"
