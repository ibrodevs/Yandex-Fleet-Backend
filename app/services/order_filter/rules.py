from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.db.models.order import Order
from app.services.order_filter.result import FilterDecision, FilterResult


class RuleResult(FilterResult):
    """Backward-compatible rule result wrapper."""

    def __init__(self, decision: FilterDecision, reasons: list[dict[str, Any]] | None = None):
        super().__init__(decision=decision, reasons=reasons or [])
        self.is_applicable = decision in {FilterDecision.ACCEPTABLE, FilterDecision.REJECTED_BY_FILTER}

    @property
    def rule_name(self) -> str:
        return "rule"


class BaseRule:
    name: str = "base"

    async def evaluate(self, order: Order, settings: Any) -> RuleResult:
        raise NotImplementedError


class MinimumPriceRule(BaseRule):
    name = "min_price"

    async def evaluate(self, order: Order, settings: Any) -> RuleResult:
        min_price = getattr(settings, "min_price", None)
        if min_price is None:
            return RuleResult(FilterDecision.ACCEPTABLE, [])

        price = order.price
        if price is None:
            return RuleResult(FilterDecision.ACCEPTABLE, [])

        if Decimal(str(price)) < Decimal(str(min_price)):
            return RuleResult(
                FilterDecision.REJECTED_BY_FILTER,
                [{"rule": self.name, "expected": str(min_price), "actual": str(price)}],
            )
        return RuleResult(FilterDecision.ACCEPTABLE, [])


class CategoryRule(BaseRule):
    name = "category"

    async def evaluate(self, order: Order, settings: Any) -> RuleResult:
        allowed = getattr(settings, "allowed_categories", None)
        blocked = getattr(settings, "blocked_categories", None) or []
        category = (order.category or "").strip()

        if blocked and category and category in set(blocked):
            return RuleResult(
                FilterDecision.REJECTED_BY_FILTER,
                [{"rule": self.name, "expected": "not_blocked", "actual": category}],
            )

        if allowed is not None and category and category not in set(allowed):
            return RuleResult(
                FilterDecision.REJECTED_BY_FILTER,
                [{"rule": self.name, "expected": list(allowed), "actual": category}],
            )

        return RuleResult(FilterDecision.ACCEPTABLE, [])


class PaymentMethodRule(BaseRule):
    name = "payment_method"

    async def evaluate(self, order: Order, settings: Any) -> RuleResult:
        blocked = getattr(settings, "blocked_payment_methods", None) or []
        allowed = getattr(settings, "allowed_payment_methods", None)
        payment_method = (order.payment_method or "").strip()

        if blocked and payment_method and payment_method in set(blocked):
            return RuleResult(
                FilterDecision.REJECTED_BY_FILTER,
                [{"rule": self.name, "expected": "not_blocked", "actual": payment_method}],
            )

        if allowed is not None and payment_method and payment_method not in set(allowed):
            return RuleResult(
                FilterDecision.REJECTED_BY_FILTER,
                [{"rule": self.name, "expected": list(allowed), "actual": payment_method}],
            )

        return RuleResult(FilterDecision.ACCEPTABLE, [])
