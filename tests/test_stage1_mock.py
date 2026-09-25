from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_mock_driver_profile():
    response = client.get("/api/v1/drivers/driver-001")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "driver-001"
    assert payload["phone"] == "+996555000001"
    assert payload["vehicle"]["brand"] == "Toyota"


def test_mock_driver_summary():
    response = client.get("/api/v1/drivers/driver-001/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["driver_id"] == "driver-001"
    assert payload["orders_total"] >= 5
    assert payload["active_orders"] >= 1
    assert payload["earnings"] > 0


def test_mock_orders_for_driver():
    response = client.get(
        "/api/v1/orders",
        params={"driver_id": "driver-001"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mock"] is True
    assert payload["total"] >= 5
    assert all(
        item["driver_id"] == "driver-001"
        for item in payload["items"]
    )


def test_mock_orders_pagination():
    first = client.get(
        "/api/v1/orders",
        params={"driver_id": "driver-001", "limit": 2, "offset": 0},
    )
    second = client.get(
        "/api/v1/orders",
        params={"driver_id": "driver-001", "limit": 2, "offset": 2},
    )

    assert first.status_code == 200
    assert second.status_code == 200

    first_ids = {item["id"] for item in first.json()["items"]}
    second_ids = {item["id"] for item in second.json()["items"]}
    assert first_ids
    assert second_ids
    assert first_ids.isdisjoint(second_ids)


def test_mock_phone_lookup():
    response = client.get(
        "/api/v1/drivers/by-phone/%2B996555000001"
    )
    assert response.status_code == 200
    assert response.json()["id"] == "driver-001"


def test_mock_order_details():
    response = client.get("/api/v1/orders/order-1006")
    assert response.status_code == 200
    order = response.json()["order"]
    assert order["driver_id"] == "driver-001"
    assert order["pickup_address"]
    assert order["destination_address"]
    assert "distance_km" in order


def test_yandex_status_reports_mock_features():
    response = client.get("/api/v1/integrations/yandex/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "mock"
    assert payload["features"]["telegram_bot"] is True
    assert payload["features"]["persistent_telegram_link"] is True
