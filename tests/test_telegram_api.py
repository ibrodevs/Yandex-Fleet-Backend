from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_telegram_status_in_local_polling_mode():
    response = client.get("/api/v1/telegram/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "polling"
    assert payload["webhook_path"] == "/api/v1/telegram/webhook"


def test_webhook_is_disabled_in_polling_mode():
    response = client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 1},
    )
    assert response.status_code == 404
