import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_telegram_status_in_local_polling_mode(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_MODE", "polling")
    get_settings.cache_clear()

    response = client.get("/api/v1/telegram/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "polling"
    assert payload["webhook_path"] == "/api/v1/telegram/webhook"


def test_webhook_is_disabled_in_polling_mode(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_MODE", "polling")
    get_settings.cache_clear()

    response = client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 1},
    )

    assert response.status_code == 404


def test_webhook_rejects_missing_secret_in_webhook_mode(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_MODE", "webhook")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    get_settings.cache_clear()

    response = client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 1},
    )

    assert response.status_code == 403
