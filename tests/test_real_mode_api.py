from fastapi.testclient import TestClient

from app.api.v1 import drivers as drivers_api
from app.api.v1 import miniapp as miniapp_api
from app.config import get_settings
from app.main import app

client = TestClient(app)


class EmptyYandexProvider:
    async def list_drivers(self):
        return []

    async def get_driver_by_phone(self, phone):
        return None

    async def get_driver(self, driver_id):
        return {
            "id": driver_id,
            "full_name": "Реальный водитель",
            "vehicle": None,
            "tariffs": [],
        }

    async def list_orders(self, **kwargs):
        return []


def test_empty_real_park_returns_200_and_phone_lookup_404(monkeypatch):
    provider = EmptyYandexProvider()
    monkeypatch.setattr(drivers_api, "get_fleet_provider", lambda: provider)
    response = client.get("/api/v1/drivers")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}
    lookup = client.get("/api/v1/drivers/by-phone/%2B996555000000")
    assert lookup.status_code == 404


def test_real_completion_is_explicitly_unsupported(monkeypatch):
    monkeypatch.setenv("YANDEX_MOCK_MODE", "false")
    get_settings.cache_clear()
    try:
        response = client.post("/api/v1/orders/order-1/complete")
        assert response.status_code == 501
        assert "не предоставляет" in response.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_real_miniapp_uses_provider_and_clean_empty_state(monkeypatch):
    provider = EmptyYandexProvider()

    async def resolved_driver(**kwargs):
        return "real-driver", {"id": 1001}, False

    monkeypatch.setenv("YANDEX_MOCK_MODE", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(miniapp_api, "_resolve_driver_id", resolved_driver)
    monkeypatch.setattr(miniapp_api, "get_fleet_provider", lambda: provider)
    try:
        response = client.get("/api/v1/miniapp/bootstrap")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mock"] is False
        assert payload["driver"]["id"] == "real-driver"
        assert payload["orders"] == []
        assert payload["summary"]["sources"] == [{"id": "yandex", "title": "Яндекс"}]
    finally:
        get_settings.cache_clear()


def test_real_miniapp_treats_yandex_work_statuses_as_active():
    orders = [
        {"id": "1", "status": "assigned", "price": 100, "currency": "RUB"},
        {"id": "2", "status": "waiting", "price": 200, "currency": "RUB"},
        {"id": "3", "status": "in_progress", "price": 300, "currency": "RUB"},
        {"id": "4", "status": "completed", "price": 400, "currency": "RUB"},
    ]

    mapped = [miniapp_api._miniapp_real_order(order) for order in orders]
    summary = miniapp_api._real_summary("real-driver", orders)

    assert [order["status"] for order in mapped[:3]] == ["active", "active", "active"]
    assert [order["status_title"] for order in mapped[:3]] == [
        "Активный",
        "Активный",
        "Активный",
    ]
    assert summary["incoming_count"] == 0
    assert summary["active_count"] == 3
    assert summary["accepted_count"] == 3
    assert summary["exact_price_count"] == 0
    assert summary["average_incoming_price"] == 0
    assert summary["by_source"] == {"yandex": 0}
