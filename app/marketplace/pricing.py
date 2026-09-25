from __future__ import annotations

from dataclasses import dataclass


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


def estimate_price(
    *,
    source: str,
    tariff: str,
    distance_km: float,
    duration_minutes: int,
    demand_multiplier: float = 1.0,
) -> float:
    """Demo estimator used only when an aggregator did not provide a price.

    It is intentionally deterministic and marked as an estimate in API output.
    Real provider quote/offer prices must replace it when integrations are added.
    """

    rate = _RATES.get(source, {}).get(tariff, _DEFAULT)
    raw = (
        rate.base
        + max(distance_km, 0) * rate.per_km
        + max(duration_minutes, 0) * rate.per_minute
    )
    raw *= max(demand_multiplier, 1.0)
    return float(max(rate.minimum, round(raw / 10) * 10))
