from app.marketplace.mock import reset_mock_marketplace_orders
from app.marketplace.pricing import estimate_price
from app.marketplace.service import (
    accept_marketplace_order,
    get_marketplace_order,
    get_marketplace_summary,
    list_marketplace_orders,
)


def test_marketplace_contains_all_demo_sources():
    items = list_marketplace_orders(driver_id="driver-001")
    assert {"fasten", "yandex", "vezet"} <= {
        item["source"] for item in items
    }


def test_marketplace_filters_fasten_incoming_orders():
    items = list_marketplace_orders(
        driver_id="driver-001",
        source="fasten",
        status="incoming",
    )
    assert items
    assert all(item["source"] == "fasten" for item in items)
    assert all(item["status"] == "incoming" for item in items)


def test_estimated_price_is_marked_separately():
    items = list_marketplace_orders(driver_id="driver-001")
    estimated = [item for item in items if item["price_is_estimated"]]
    exact = [item for item in items if not item["price_is_estimated"]]

    assert estimated
    assert exact
    assert all(item["price_label"].startswith("≈") for item in estimated)
    assert all(item["price_calculation"] for item in estimated)
    assert all(not item["price_label"].startswith("≈") for item in exact)
    assert all(item["price_calculation"] is None for item in exact)


def test_price_estimator_is_deterministic():
    price = estimate_price(
        source="fasten",
        tariff="comfort",
        distance_km=8.6,
        duration_minutes=19,
        demand_multiplier=1.15,
    )
    assert price > 0
    assert price % 10 == 0


def test_marketplace_summary_and_details():
    summary = get_marketplace_summary("driver-001")
    order = get_marketplace_order("market-2001", driver_id="driver-001")

    assert summary["incoming_count"] >= 1
    assert summary["by_source"]["fasten"] >= 1
    assert order is not None
    assert order["source"] == "fasten"


def test_accept_incoming_marketplace_order():
    reset_mock_marketplace_orders()
    try:
        before = get_marketplace_order(
            "market-2001",
            driver_id="driver-001",
        )
        assert before is not None
        assert before["status"] == "incoming"
        assert before["can_accept"] is True

        accepted = accept_marketplace_order(
            "market-2001",
            driver_id="driver-001",
        )

        assert accepted["status"] == "accepted"
        assert accepted["status_title"] == "Принят"
        assert accepted["can_accept"] is False
        assert accepted["accepted_at"]

        summary = get_marketplace_summary("driver-001")
        assert summary["accepted_count"] >= 2
    finally:
        reset_mock_marketplace_orders()
