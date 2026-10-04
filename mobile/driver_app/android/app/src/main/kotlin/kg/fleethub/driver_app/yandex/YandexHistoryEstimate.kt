package kg.fleethub.driver_app.yandex

import kotlin.math.ceil
import kotlin.math.floor

/** A broad orientation from this driver's completed rides, never a quoted Yandex fare. */
data class CompletedRideSample(
    val tariff: String,
    val price: Double,
    val currency: String?,
    val durationMinutes: Int?,
)

data class EstimateRange(val low: Int, val high: Int, val currency: String? = null)

object YandexHistoryEstimate {
    private fun tariffKey(value: String?): String? = value?.trim()?.lowercase()
        ?.takeIf { it.isNotBlank() && it != "—" }

    private fun range(values: List<Double>, currency: String? = null): EstimateRange? {
        if (values.isEmpty()) return null
        val sorted = values.sorted()
        val middle = sorted[sorted.size / 2]
        val spread = if (sorted.size >= 3) 0.35 else 0.50
        val low = floor(minOf(sorted.first(), middle * (1 - spread))).toInt().coerceAtLeast(1)
        val high = ceil(maxOf(sorted.last(), middle * (1 + spread))).toInt()
        return EstimateRange(low, high, currency)
    }

    fun price(samples: List<CompletedRideSample>, tariff: String?, currency: String?): EstimateRange? {
        val key = tariffKey(tariff) ?: return null
        val matching = samples.filter { tariffKey(it.tariff) == key && it.price.isFinite() && it.price > 0 }
        val knownCurrency = currency?.takeIf { it.isNotBlank() }
        val historyCurrencies = matching.mapNotNull { it.currency?.takeIf(String::isNotBlank) }.distinct()
        if (knownCurrency == null && historyCurrencies.size > 1) return null
        val selectedCurrency = knownCurrency ?: historyCurrencies.singleOrNull()
        val selected = matching.filter { it.currency == selectedCurrency }
        if (selected.isEmpty()) return null
        return range(selected.map { it.price }, selected.first().currency)
    }

    fun duration(samples: List<CompletedRideSample>, tariff: String?): EstimateRange? {
        val key = tariffKey(tariff) ?: return null
        return range(samples.filter { tariffKey(it.tariff) == key }
            .mapNotNull { it.durationMinutes?.takeIf { minutes -> minutes in 1..240 }?.toDouble() })
    }
}
