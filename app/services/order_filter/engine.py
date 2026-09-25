from __future__ import annotations

from typing import Any

from app.services.order_filter.result import FilterDecision, FilterResult
from app.services.order_filter.rules import CategoryRule, MinimumPriceRule, PaymentMethodRule


class OrderFilterEngine:
    def __init__(self, rules: list[Any] | None = None):
        self.rules = rules or [MinimumPriceRule(), CategoryRule(), PaymentMethodRule()]

    async def evaluate(self, driver: Any, order: Any, settings: Any) -> FilterResult:
        all_reasons: list[dict[str, Any]] = []

        for rule in self.rules:
            result = await rule.evaluate(order, settings)
            if result.decision == FilterDecision.REJECTED_BY_FILTER:
                all_reasons.extend(result.reasons)

        if all_reasons:
            return FilterResult(
                decision=FilterDecision.REJECTED_BY_FILTER,
                reasons=all_reasons,
            )

        return FilterResult(decision=FilterDecision.ACCEPTABLE, reasons=[])
