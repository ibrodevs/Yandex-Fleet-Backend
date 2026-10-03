import asyncio
import time
from copy import deepcopy

import httpx
import pytest

from app.config import Settings
from app.core.exceptions import YandexRateLimitError
from app.services.fleet.base import FleetProviderError
from app.services.fleet.phone import normalize_phone
from app.services.fleet.yandex import YandexFleetProvider
from app.services.yandex.cache import SharedYandexCache
from app.services.yandex.client import YandexFleetClient
from tests.test_yandex_mappers import driver_fixture, order_fixture


class FakeYandexClient:
    def __init__(self, profiles=None, orders=None, cars=None):
        self.profiles = profiles or []
        self.orders = orders or []
        self.cars = cars or []
        self.order_calls = []
        self.profile_calls = 0
        self.search_calls = []

    async def list_driver_profiles(
        self,
        *,
        driver_profile_ids=None,
        search_text=None,
        max_records=None,
        retry_safe=True,
    ):
        self.profile_calls += 1
        if search_text:
            self.search_calls.append(search_text)
        items = deepcopy(self.profiles)
        if driver_profile_ids:
            items = [item for item in items if item["driver_profile"]["id"] in driver_profile_ids]
        if search_text:
            items = [
                item for item in items
                if search_text in {
                    normalize_phone(phone) for phone in item["driver_profile"].get("phones", [])
                }
            ]
        return items[:max_records] if max_records else items

    async def list_orders(self, **kwargs):
        self.order_calls.append(kwargs)
        items = deepcopy(self.orders)
        if kwargs.get("driver_profile_id"):
            items = [
                item
                for item in items
                if item.get("driver_profile", {}).get("id") == kwargs["driver_profile_id"]
            ]
        if kwargs.get("order_ids"):
            items = [item for item in items if item.get("id") in kwargs["order_ids"]]
        return items

    async def list_cars(self, *, car_ids=None, max_records=None):
        items = deepcopy(self.cars)
        if car_ids:
            items = [item for item in items if item.get("id") in car_ids]
        return items[:max_records] if max_records else items

    async def get_order_track(self, order_id):
        return {"track": [{"order_status": "complete"}]}

    async def aclose(self):
        return None


def settings(tmp_path, **overrides):
    values = dict(
        YANDEX_CLIENT_ID="test-client",
        YANDEX_API_KEY="test-key",
        YANDEX_PARK_ID="test-park",
        YANDEX_MOCK_MODE=False,
        YANDEX_CACHE_DB_PATH=str(tmp_path / "yandex-cache.sqlite3"),
    )
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_empty_park_is_valid(tmp_path):
    client = FakeYandexClient()
    provider = YandexFleetProvider(client, settings=settings(tmp_path))
    assert await provider.list_drivers() == []
    assert await provider.get_driver("missing") is None
    assert await provider.get_driver_by_phone("0555000000") is None
    assert client.profile_calls == 1


@pytest.mark.asyncio
async def test_driver_lookup_and_phone_exact_normalized_match(tmp_path):
    client = FakeYandexClient(profiles=[driver_fixture()])
    provider = YandexFleetProvider(client, settings=settings(tmp_path))
    assert (await provider.get_driver("driver-1"))["id"] == "driver-1"
    assert (await provider.get_driver_by_phone("+996555123456"))["id"] == "driver-1"
    assert (await provider.get_driver_by_phone("0555 123 456"))["id"] == "driver-1"
    assert await provider.get_driver_by_phone("+996700000000") is None
    assert client.profile_calls == 1


@pytest.mark.asyncio
async def test_cold_login_searches_exact_phone_without_loading_park_snapshot(tmp_path):
    client = FakeYandexClient(profiles=[driver_fixture()])
    provider = YandexFleetProvider(client, settings=settings(tmp_path))

    driver = await provider.get_driver_by_phone("+996555123456")

    assert driver["id"] == "driver-1"
    assert client.search_calls == ["+996555123456"]
    assert client.profile_calls == 1
    assert await provider.cache.get("drivers:park:default") is None


@pytest.mark.asyncio
async def test_driver_snapshot_refreshes_after_ttl(tmp_path):
    now = [100.0]
    client = FakeYandexClient(profiles=[driver_fixture()])
    cfg = settings(tmp_path, YANDEX_DRIVER_CACHE_TTL_SECONDS=10)
    cache = SharedYandexCache(cfg.YANDEX_CACHE_DB_PATH, clock=lambda: now[0])
    provider = YandexFleetProvider(client, settings=cfg, cache=cache)

    await provider.list_drivers()
    now[0] += 5
    await provider.get_driver("driver-1")
    now[0] += 6
    await provider.get_driver_by_phone("+996555123456")

    assert client.profile_calls == 2


@pytest.mark.asyncio
async def test_vehicle_listing_and_lookup_are_mapped(tmp_path):
    car = driver_fixture()["car"]
    provider = YandexFleetProvider(
        FakeYandexClient(cars=[car]),
        settings=settings(tmp_path),
    )

    assert (await provider.list_vehicles())[0]["plate"] == "01KG001ABC"
    assert (await provider.get_vehicle("car-1"))["brand"] == "Toyota"
    assert await provider.get_vehicle("missing") is None


@pytest.mark.asyncio
async def test_provider_filters_orders_and_enforces_result_ownership(tmp_path):
    own = order_fixture()
    foreign = deepcopy(own)
    foreign["id"] = "order-2"
    foreign["driver_profile"] = {"id": "driver-2", "name": "Другой"}
    client = FakeYandexClient(orders=[own, foreign])
    provider = YandexFleetProvider(client, settings=settings(tmp_path))
    items = await provider.list_orders(driver_id="driver-1")
    assert [item["id"] for item in items] == ["order-1"]
    assert client.order_calls[0].get("driver_profile_id") is None
    assert len(await provider.list_orders()) == 2
    assert len(client.order_calls) == 1


@pytest.mark.asyncio
async def test_get_order_loads_track_only_for_details(tmp_path):
    client = FakeYandexClient(orders=[order_fixture()])
    provider = YandexFleetProvider(client, settings=settings(tmp_path))
    order = await provider.get_order("order-1")
    assert order["track"] == [{"order_status": "complete"}]


@pytest.mark.asyncio
async def test_real_summary_and_unsupported_completion(tmp_path):
    client = FakeYandexClient(profiles=[driver_fixture()], orders=[order_fixture()])
    provider = YandexFleetProvider(client, settings=settings(tmp_path))
    summary = await provider.get_driver_summary("driver-1")
    assert summary["completed_orders"] == 1
    assert summary["earnings"] == 450.5
    with pytest.raises(FleetProviderError, match="не поддерживается"):
        await provider.complete_order("order-1")


@pytest.mark.asyncio
async def test_concurrent_standard_reads_share_single_orders_refresh(tmp_path):
    own = order_fixture()
    client = FakeYandexClient(profiles=[driver_fixture()], orders=[own])
    provider = YandexFleetProvider(client, settings=settings(tmp_path))

    all_orders, owned_orders, summary = await asyncio.gather(
        provider.list_orders(),
        provider.list_orders(driver_id="driver-1"),
        provider.get_driver_summary("driver-1"),
    )

    assert [item["id"] for item in all_orders] == ["order-1"]
    assert [item["id"] for item in owned_orders] == ["order-1"]
    assert summary["orders_total"] == 1
    assert len(client.order_calls) == 1
    assert client.profile_calls == 1


@pytest.mark.asyncio
async def test_too_old_orders_snapshot_preserves_provider_error(tmp_path):
    now = [100.0]

    class FailingOrdersClient(FakeYandexClient):
        async def list_orders(self, **kwargs):
            if self.order_calls:
                raise YandexRateLimitError()
            return await super().list_orders(**kwargs)

    client = FailingOrdersClient(orders=[order_fixture()])
    cfg = settings(
        tmp_path,
        YANDEX_ORDERS_CACHE_TTL_SECONDS=10,
        YANDEX_CACHE_STALE_SECONDS=60,
    )
    cache = SharedYandexCache(cfg.YANDEX_CACHE_DB_PATH, clock=lambda: now[0])
    provider = YandexFleetProvider(client, settings=cfg, cache=cache)
    await provider.list_orders()
    now[0] += 71

    with pytest.raises(FleetProviderError, match="ограничил частоту"):
        await provider.list_orders()


@pytest.mark.asyncio
async def test_stale_orders_skip_long_retry_after_and_can_refresh_later(tmp_path):
    now = [100.0]
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "60"},
                json={"message": "Slow down"},
                request=request,
            )
        fresh = order_fixture()
        fresh["id"] = "order-fresh"
        return httpx.Response(
            200,
            json={"orders": [fresh]},
            request=request,
        )

    cfg = settings(
        tmp_path,
        YANDEX_RETRY_ATTEMPTS=3,
        YANDEX_ORDERS_CACHE_TTL_SECONDS=10,
        YANDEX_CACHE_STALE_SECONDS=60,
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = YandexFleetClient(
        http,
        settings=cfg,
        jitter=lambda _start, _end: 0.1,
    )
    cache = SharedYandexCache(cfg.YANDEX_CACHE_DB_PATH, clock=lambda: now[0])
    await cache.set("orders:park:default", [order_fixture()])
    now[0] += 11
    provider = YandexFleetProvider(client, settings=cfg, cache=cache)

    started = time.monotonic()
    stale = await asyncio.wait_for(provider.list_orders(), timeout=0.5)

    assert time.monotonic() - started < 0.5
    assert [item["id"] for item in stale] == ["order-1"]
    assert request_count == 1

    refreshed = await provider.list_orders()
    assert [item["id"] for item in refreshed] == ["order-fresh"]
    assert request_count == 2
    await http.aclose()
