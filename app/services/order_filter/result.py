from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FilterDecision(StrEnum):
    ACCEPTABLE = "acceptable"
    REJECTED_BY_FILTER = "rejected_by_filter"
    MANUAL_REVIEW = "manual_review"


@dataclass
class FilterResult:
    decision: FilterDecision
    reasons: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reasons": self.reasons,
        }
