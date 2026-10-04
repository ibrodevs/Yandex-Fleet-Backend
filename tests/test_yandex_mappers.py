from app.services.fleet.phone import normalize_phone
from app.services.fleet.yandex_mappers import (
    map_yandex_driver,
    map_yandex_driver_summary,
    map_yandex_order,
    map_yandex_vehicle,
)


def driver_fixture():
    return {
        "accounts": [{"type": "current", "balance": "700.5000", "currency": "KGS"}],
        "car": {
            "id": "car-1",
            "status": "working",
            "category": ["econom", "comfort"],
            "brand": "Toyota",
            "model": "Camry",
            "year": 2022,
            "color": "Белый",
            "number": "01KG001ABC",
        },
        "current_status": {"status": "free"},
        "driver_profile": {
            "id": "driver-1",
            "last_name": "Иванов",
            "first_name": "Иван",
            "middle_name": "Иванович",
            "phones": ["0555 123-456"],
            "work_status": "working",
            "work_rule_id": "rule-1",
        },
    }


def order_fixture(status="complete"):
    return {
        "id": "order-1",
        "short_id": 42,
        "status": status,
        "created_at": "2026-09-26T10:00:00+00:00",
        "booked_at": "2026-09-26T10:05:00+00:00",
        "ended_at": "2026-09-26T10:35:00+00:00",
        "provider": "platform",
        "category": "comfort",
        "address_from": {"address": "Точка А", "lat": 1, "lon": 2},
        "route_points": [{"address": "Точка Б", "lat": 3, "lon": 4}],
        "events": [{"event_at": "2026-09-26T10:10:00+00:00", "order_status": "transporting"}],
        "payment_method": "cashless",
        "driver_profile": {"id": "driver-1", "name": "Иванов Иван"},
        "car": {"id": "car-1", "brand_model": "Toyota Camry", "license": {"number": "01KG001ABC"}},
        "price": "450.50",
        "mileage": "12.4",
    }


def test_phone_normalization_exact_international_and_local():
    assert normalize_phone("+996 555-123-456") == "+996555123456"
    assert normalize_phone("996555123456") == "+996555123456"
    assert normalize_phone("0555123456") == "+996555123456"
    assert normalize_phone("+7 (999) 123-45-67") == "+79991234567"
    assert normalize_phone("invalid") is None


def test_driver_and_vehicle_mapping_preserve_real_values_and_missing_fields():
    driver = map_yandex_driver(driver_fixture())
    assert driver["id"] == "driver-1"
    assert driver["full_name"] == "Иванов Иван Иванович"
    assert driver["phone"] == "+996555123456"
    assert driver["balance"] == 700.5
    assert driver["rating"] is None
    assert driver["priority_points"] is None
    assert driver["vehicle"]["plate"] == "01KG001ABC"
    assert driver["tariffs"] == ["Эконом", "Комфорт"]
    assert map_yandex_vehicle(None) is None


def test_driver_mapping_handles_nested_blocks_and_preserves_sync_timestamps():
    raw = driver_fixture()
    raw["updated_at"] = "2026-09-27T08:00:00Z"
    raw["current_status"]["status_updated_at"] = "2026-09-27T07:59:00Z"

    driver = map_yandex_driver(raw)

    assert driver["updated_at"] == "2026-09-27T08:00:00Z"
    assert driver["status_updated_at"] == "2026-09-27T07:59:00Z"
    assert map_yandex_driver({"driver_profile": None, "accounts": {}})["id"] == ""


def test_order_mapping_route_price_payment_status_and_timestamps():
    order = map_yandex_order(order_fixture())
    assert order["status"] == "completed"
    assert order["pickup_address"] == "Точка А"
    assert order["destination_address"] == "Точка Б"
    assert order["price"] == 450.5
    assert order["payment_method"] == "cashless"
    assert order["payment_category"] == "cashless"
    assert order["currency"] is None
    assert order["data_kind"] == "confirmed_order"
    assert order["distance_km"] == 12.4
    assert order["duration_minutes"] == 30
    assert order["started_at"] == "2026-09-26T10:10:00+00:00"
    assert order["can_complete"] is False


def test_unknown_order_status_is_safe_and_missing_fields_remain_empty():
    order = map_yandex_order({"id": "order-x", "status": "future_status"})
    assert order["status"] == "unknown"
    assert order["status"] != "completed"
    assert order["price"] is None
    assert order["destination_address"] is None


def test_yandex_order_preserves_original_payment_and_only_explicit_currency():
    raw = order_fixture()
    raw["payment_method"] = "prepaid"
    raw["currency"] = "KGS"
    mapped = map_yandex_order(raw)
    assert mapped["payment_method"] == "prepaid"
    assert mapped["payment_category"] == "prepaid"
    assert mapped["currency"] == "KGS"

    raw.pop("currency")
    assert map_yandex_order(raw)["currency"] is None


def test_driver_summary_only_uses_owned_known_data():
    completed = map_yandex_order(order_fixture())
    foreign = dict(completed, id="foreign", driver_id="driver-2", price=999)
    cancelled = dict(completed, id="cancelled", status="cancelled", price=None)
    summary = map_yandex_driver_summary(
        "driver-1",
        [completed, foreign, cancelled],
        currency="KGS",
    )
    assert summary["orders_total"] == 2
    assert summary["completed_orders"] == 1
    assert summary["cancelled_orders"] == 1
    assert summary["earnings"] == 450.5
    assert summary["distance_km"] == 12.4
