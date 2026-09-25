from decimal import Decimal

import pytest

from app.db.models.order import Order
from app.services.order_filter.engine import OrderFilterEngine
from app.services.order_filter.result import FilterDecision
from app.services.order_filter.rules import (
    CategoryRule,
    MinimumPriceRule,
    PaymentMethodRule,
)


@pytest.mark.asyncio
async def test_minimum_price_rule_rejects_below_threshold():
    order = Order(
        yandex_order_id="order-1",
        price=Decimal("340"),
        category="econom",
        payment_method="cash",
    )
    settings = type(
        "Settings",
        (),
        {"min_price": Decimal("500"), "allowed_categories": None, "blocked_categories": None, "allowed_payment_methods": None, "blocked_payment_methods": None},
    )()

    result = await MinimumPriceRule().evaluate(order, settings)

    assert result.is_applicable is True
    assert result.decision == FilterDecision.REJECTED_BY_FILTER
    assert result.reasons[0]["rule"] == "min_price"


@pytest.mark.asyncio
async def test_category_rule_rejects_blocked_category():
    order = Order(yandex_order_id="order-2", category="vip")
    settings = type("Settings", (), {"blocked_categories": ["vip"], "allowed_categories": None})()

    result = await CategoryRule().evaluate(order, settings)

    assert result.decision == FilterDecision.REJECTED_BY_FILTER


@pytest.mark.asyncio
async def test_payment_method_rule_rejects_blocked_payment_method():
    order = Order(yandex_order_id="order-3", payment_method="cash")
    settings = type("Settings", (), {"blocked_payment_methods": ["cash"]})()

    result = await PaymentMethodRule().evaluate(order, settings)

    assert result.decision == FilterDecision.REJECTED_BY_FILTER


@pytest.mark.asyncio
async def test_filter_engine_accepts_valid_order():
    order = Order(
        yandex_order_id="order-4",
        price=Decimal("800"),
        category="econom",
        payment_method="card",
    )
    settings = type(
        "Settings",
        (),
        {
            "min_price": Decimal("500"),
            "allowed_categories": ["econom"],
            "blocked_categories": [],
            "allowed_payment_methods": ["card"],
            "blocked_payment_methods": [],
            "max_pickup_distance_km": None,
        },
    )()

    result = await OrderFilterEngine().evaluate(None, order, settings)

    assert result.decision == FilterDecision.ACCEPTABLE
    assert result.reasons == []
