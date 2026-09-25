from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_mock_driver_profile():
    response = client.get("/api/v1/drivers/driver-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "driver-001"
    assert payload["phone"] == "+996555000001"


def test_mock_orders_for_driver():
    response = client.get(
        "/api/v1/orders",
        params={"driver_id": "driver-001"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mock"] is True
    assert payload["total"] >= 1
    assert all(
        item["driver_id"] == "driver-001"
        for item in payload["items"]
    )


def test_mock_phone_lookup():
    response = client.get(
        "/api/v1/drivers/by-phone/%2B996555000001"
    )
    assert response.status_code == 200
    assert response.json()["id"] == "driver-001"
