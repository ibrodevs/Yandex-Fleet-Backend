from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.marketplace.mock import reset_mock_marketplace_orders

client = TestClient(app)


def test_miniapp_static_page_is_served():
    response = client.get("/miniapp/", follow_redirects=True)
    assert response.status_code == 200
    assert "Поступающие заказы" in response.text
    assert "telegram-web-app.js" in response.text
    assert 'id="i-orders"' in response.text
    assert "bottom-nav" in response.text
    assert 'id="settingsView"' in response.text
    assert 'id="incomingLayer"' in response.text


def test_miniapp_demo_bootstrap(monkeypatch):
    monkeypatch.setenv("YANDEX_MOCK_MODE", "true")
    monkeypatch.setenv("TELEGRAM_MINI_APP_DEMO_MODE", "true")
    get_settings.cache_clear()

    try:
        response = client.get("/api/v1/miniapp/bootstrap?demo=true")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "demo"
        assert payload["driver"]["id"] == "driver-001"
        assert {"fasten", "yandex", "vezet"} <= {
            item["source"] for item in payload["orders"]
        }
    finally:
        get_settings.cache_clear()


def test_miniapp_demo_can_be_disabled(monkeypatch):
    monkeypatch.setenv("YANDEX_MOCK_MODE", "true")
    monkeypatch.setenv("TELEGRAM_MINI_APP_DEMO_MODE", "false")
    get_settings.cache_clear()

    try:
        response = client.get("/api/v1/miniapp/bootstrap?demo=true")
        assert response.status_code == 403
    finally:
        get_settings.cache_clear()


def test_miniapp_javascript_uses_svg_icons_without_emoji():
    response = client.get("/miniapp/app.js")
    assert response.status_code == 200
    assert 'href="#i-' in response.text
    for emoji in ("📍", "⏱", "💵", "💳", "⭐", "🚕", "📊", "👤"):
        assert emoji not in response.text


def test_miniapp_has_configurable_incoming_window_and_stats():
    response = client.get("/miniapp/app.js")
    assert response.status_code == 200
    assert "fleet-hub-incoming-settings-v1" in response.text
    assert "showIncoming" in response.text
    assert "Последние 7 дней" in response.text
    assert "Проверить окно" in response.text


def test_miniapp_demo_order_lifecycle(monkeypatch):
    monkeypatch.setenv("YANDEX_MOCK_MODE", "true")
    monkeypatch.setenv("TELEGRAM_MINI_APP_DEMO_MODE", "true")
    get_settings.cache_clear()
    reset_mock_marketplace_orders()

    try:
        accepted = client.post(
            "/api/v1/miniapp/orders/market-2002/accept?demo=true"
        )
        assert accepted.status_code == 200
        payload = accepted.json()
        assert payload["ok"] is True
        assert payload["order"]["status"] == "active"
        assert payload["order"]["can_accept"] is False
        assert payload["order"]["can_complete"] is True
        assert payload["summary"]["active_count"] == 1

        blocked = client.post(
            "/api/v1/miniapp/orders/market-2003/accept?demo=true"
        )
        assert blocked.status_code == 409

        completed = client.post(
            "/api/v1/miniapp/orders/market-2002/complete?demo=true"
        )
        assert completed.status_code == 200
        completed_payload = completed.json()
        assert completed_payload["order"]["status"] == "completed"
        assert completed_payload["order"]["can_complete"] is False
        assert completed_payload["summary"]["active_count"] == 0

        repeat = client.post(
            "/api/v1/miniapp/orders/market-2002/complete?demo=true"
        )
        assert repeat.status_code == 409

        next_order = client.post(
            "/api/v1/miniapp/orders/market-2003/accept?demo=true"
        )
        assert next_order.status_code == 200
        assert next_order.json()["order"]["status"] == "active"
    finally:
        reset_mock_marketplace_orders()
        get_settings.cache_clear()
