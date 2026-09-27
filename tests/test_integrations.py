from fastapi.testclient import TestClient

from app.api.v1 import integrations as integrations_api
from app.config import get_settings
from app.main import app

client = TestClient(app)


class SuccessfulYandexClient:
    def __init__(self, **kwargs):
        pass

    async def list_driver_profiles(self, *, max_records=None):
        return [{"driver_profile": {"id": "real-driver"}}]

    async def aclose(self):
        return None


def test_yandex_status_reports_successful_sync_timestamp(monkeypatch):
    monkeypatch.setenv("YANDEX_MOCK_MODE", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(integrations_api, "YandexFleetClient", SuccessfulYandexClient)
    try:
        response = client.get("/api/v1/integrations/yandex/status")
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "yandex"
        assert payload["last_successful_sync"] is not None
        assert payload["last_sync_error"] is None
    finally:
        get_settings.cache_clear()
