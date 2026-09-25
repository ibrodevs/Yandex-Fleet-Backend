from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TariffRate:
    base: float
    per_km: float
    per_minute: float
    minimum: float


_RATES: dict[str, dict[str, TariffRate]] = {
    "yandex": {
        "econom": TariffRate(base=75, per_km=24, per_minute=4.5, minimum=150),
        "comfort": TariffRate(base=105, per_km=31, per_minute=5.5, minimum=210),
        "comfort_plus": TariffRate(base=150, per_km=42, per_minute=7, minimum=300),
    },
    "fasten": {
        "econom": TariffRate(base=70, per_km=23, per_minute=4.0, minimum=145),
        "comfort": TariffRate(base=100, per_km=30, per_minute=5.0, minimum=205),
        "business": TariffRate(base=185, per_km=48, per_minute=8.0, minimum=360),
    },
    "vezet": {
        "econom": TariffRate(base=65, per_km=22, per_minute=3.8, minimum=140),
        "comfort": TariffRate(base=95, per_km=28, per_minute=4.8, minimum=195),
    },
}

_DEFAULT = TariffRate(base=75, per_km=24, per_minute=4.5, minimum=150)


def estimate_price_details(
    *,
    source: str,
    tariff: str,
    distance_km: float,
    duration_minutes: int,
    demand_multiplier: float = 1.0,
) -> dict[str, Any]:
    rate = _RATES.get(source, {}).get(tariff, _DEFAULT)
    distance_part = max(distance_km, 0) * rate.per_km
    time_part = max(duration_minutes, 0) * rate.per_minute
    subtotal = rate.base + distance_part + time_part
    multiplier = max(demand_multiplier, 1.0)
    multiplied = subtotal * multiplier
    total = float(max(rate.minimum, round(multiplied / 10) * 10))

    return {
        "base": rate.base,
        "per_km": rate.per_km,
        "per_minute": rate.per_minute,
        "distance_part": round(distance_part, 2),
        "time_part": round(time_part, 2),
        "demand_multiplier": round(multiplier, 2),
        "minimum": rate.minimum,
        "subtotal": round(subtotal, 2),
        "total": total,
        "currency": "KGS",
        "is_demo_formula": True,
    }


def estimate_price(
    *,
    source: str,
    tariff: str,
    distance_km: float,
    duration_minutes: int,
    demand_multiplier: float = 1.0,
) -> float:
    """Demo estimator used only when an aggregator did not provide a price."""

    return float(
        estimate_price_details(
            source=source,
            tariff=tariff,
            distance_km=distance_km,
            duration_minutes=duration_minutes,
            demand_multiplier=demand_multiplier,
        )["total"]
    )
