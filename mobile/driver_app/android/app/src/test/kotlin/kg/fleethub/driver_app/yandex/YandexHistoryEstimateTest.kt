package kg.fleethub.driver_app.yandex

import org.junit.Assert.*
import org.junit.Test

class YandexHistoryEstimateTest {
    private val rides = listOf(
        CompletedRideSample("Комфорт", 400.0, "RUB", 20),
        CompletedRideSample("Комфорт", 500.0, "RUB", 25),
        CompletedRideSample("Комфорт", 600.0, "RUB", 30),
        CompletedRideSample("Комфорт+", 900.0, "RUB", 40),
        CompletedRideSample("Комфорт", 1200.0, "KGS", 26),
    )

    @Test fun estimateIsBroadAndNeverUsesPickupTimeOrAnotherTariff() {
        val fare = YandexHistoryEstimate.price(rides, "Комфорт", "RUB")!!
        assertEquals("RUB", fare.currency)
        assertTrue(fare.low <= 400)
        assertTrue(fare.high >= 600)
        val duration = YandexHistoryEstimate.duration(rides, "Комфорт")!!
        assertTrue(duration.low <= 20)
        assertTrue(duration.high >= 30)
        assertNull(YandexHistoryEstimate.price(rides, "Эконом", "RUB"))
    }

    @Test fun mixedOrUnknownCurrenciesCannotBeSilentlyCombined() {
        assertNull(YandexHistoryEstimate.price(rides, "Комфорт", null))
        val som = YandexHistoryEstimate.price(rides, "Комфорт", "KGS")!!
        assertEquals("KGS", som.currency)
        assertTrue(som.low <= 1200 && som.high >= 1200)
        assertNull(YandexHistoryEstimate.price(emptyList(), "Комфорт", "RUB"))
    }
}
