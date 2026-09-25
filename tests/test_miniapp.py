from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


def test_miniapp_static_page_is_served():
    response = client.get("/miniapp/", follow_redirects=True)
    assert response.status_code == 200
    assert "Поступающие заказы" in response.text
    assert "telegram-web-app.js" in response.text


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
