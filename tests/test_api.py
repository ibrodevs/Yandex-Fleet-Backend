from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_orders_endpoint():
    response = client.get("/api/v1/orders")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


def test_yandex_status_endpoint():
    response = client.get("/api/v1/integrations/yandex/status")
    assert response.status_code == 200
    payload = response.json()
    assert "features" in payload
    assert payload["features"]["incoming_offers"] is False
