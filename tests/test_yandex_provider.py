from copy import deepcopy

import pytest

from app.config import Settings
from app.services.fleet.base import FleetProviderError
from app.services.fleet.yandex import YandexFleetProvider
from tests.test_yandex_mappers import driver_fixture, order_fixture


class FakeYandexClient:
    def __init__(self, profiles=None, orders=None):
        self.profiles = profiles or []
        self.orders = orders or []
        self.order_calls = []

    async def list_driver_profiles(self, *, driver_profile_ids=None, max_records=None):
        items = deepcopy(self.profiles)
        if driver_profile_ids:
            items = [item for item in items if item["driver_profile"]["id"] in driver_profile_ids]
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

    async def get_order_track(self, order_id):
        return {"track": [{"order_status": "complete"}]}

    async def aclose(self):
        return None


def settings():
    return Settings(
        YANDEX_CLIENT_ID="test-client",
        YANDEX_API_KEY="test-key",
        YANDEX_PARK_ID="test-park",
        YANDEX_MOCK_MODE=False,
    )


@pytest.mark.asyncio
async def test_empty_park_is_valid():
    provider = YandexFleetProvider(FakeYandexClient(), settings=settings())
    assert await provider.list_drivers() == []
    assert await provider.get_driver("missing") is None
    assert await provider.get_driver_by_phone("0555000000") is None


@pytest.mark.asyncio
async def test_driver_lookup_and_phone_exact_normalized_match():
    client = FakeYandexClient(profiles=[driver_fixture()])
    provider = YandexFleetProvider(client, settings=settings())
    assert (await provider.get_driver("driver-1"))["id"] == "driver-1"
    assert (await provider.get_driver_by_phone("+996555123456"))["id"] == "driver-1"
    assert (await provider.get_driver_by_phone("0555 123 456"))["id"] == "driver-1"
    assert await provider.get_driver_by_phone("+996700000000") is None


@pytest.mark.asyncio
async def test_provider_filters_orders_and_enforces_result_ownership():
    own = order_fixture()
    foreign = deepcopy(own)
    foreign["id"] = "order-2"
    foreign["driver_profile"] = {"id": "driver-2", "name": "Другой"}
    client = FakeYandexClient(orders=[own, foreign])
    provider = YandexFleetProvider(client, settings=settings())
    items = await provider.list_orders(driver_id="driver-1")
    assert [item["id"] for item in items] == ["order-1"]
    assert client.order_calls[0]["driver_profile_id"] == "driver-1"


@pytest.mark.asyncio
async def test_get_order_loads_track_only_for_details():
    client = FakeYandexClient(orders=[order_fixture()])
    provider = YandexFleetProvider(client, settings=settings())
    order = await provider.get_order("order-1")
    assert order["track"] == [{"order_status": "complete"}]


@pytest.mark.asyncio
async def test_real_summary_and_unsupported_completion():
    client = FakeYandexClient(profiles=[driver_fixture()], orders=[order_fixture()])
    provider = YandexFleetProvider(client, settings=settings())
    summary = await provider.get_driver_summary("driver-1")
    assert summary["completed_orders"] == 1
    assert summary["earnings"] == 450.5
    with pytest.raises(FleetProviderError, match="не поддерживается"):
        await provider.complete_order("order-1")
