package kg.fleethub.driver_app.yandex

import org.junit.Assert.*
import org.junit.Test

class YandexOrderDetectorTest {
    private fun payload(title: String, text: String = "") = YandexNotificationPayload(
        "ru.yandex.taximeter", "key", 123L, title, text, "", "", null)

    @Test fun confirmsOfferWithoutTreatingBareAmountAsFare() {
        val result = YandexOrderDetector.detect(payload("Новый заказ", "350 ₽"))
        assertTrue(result.isOrder)
        assertEquals("high", result.confidence)
        assertNull(result.price)
        assertNull(result.currency)
        assertNull(result.pickup)
        assertNull(result.destination)
    }

    @Test fun readsExplicitNotificationFareAndCurrency() {
        val result = YandexOrderDetector.detect(payload("Новый заказ", "Цена поездки: 350 сом"))
        assertTrue(result.isOrder)
        assertEquals("350", result.price)
        assertEquals("KGS", result.currency)
    }

    @Test fun acceptsExactYandexOfferWithoutPriceOrAddress() {
        val result = YandexOrderDetector.detect(payload("Яндекс Про", "Новый заказ"))
        assertTrue(result.isOrder)
        assertEquals("high", result.confidence)
        assertNull(result.price)
        assertNull(result.pickup)
    }

    @Test fun rejectsServiceMessagesAndNonExactOfferPhrases() {
        assertFalse(YandexOrderDetector.detect(payload("Яндекс Про", "Новый заказ в городе")).isOrder)
        assertFalse(YandexOrderDetector.detect(payload("Заказ отменён", "350 ₽")).isOrder)
        assertFalse(YandexOrderDetector.detect(payload("Новости сервиса", "350 ₽")).isOrder)
        assertFalse(YandexOrderDetector.detect(payload("Новости сервиса", "Новый заказ")).isOrder)
    }

    @Test fun acceptsAddressWithoutPrice() {
        val result = YandexOrderDetector.detect(payload("Заказ для вас", "ул. Манаса 45"))
        assertTrue(result.isOrder)
        assertEquals("high", result.confidence)
        assertEquals("ул. Манаса 45", result.pickup)
        assertNull(result.price)
    }

    @Test fun mediumOfferIsLoggedButNotDelivered() {
        val result = YandexOrderDetector.detect(payload("Предложение заказа"))
        assertFalse(result.isOrder)
        assertEquals("medium", result.confidence)
    }

    @Test fun reusedNotificationKeyCreatesNewEventAfterStatusTransition() {
        val first = YandexOfferTracker.transition(YandexOfferState(), true, false, 1_000L)
        val update = YandexOfferTracker.transition(first, true, false, 2_000L)
        val idle = YandexOfferTracker.transition(update, false, true, 3_000L)
        val second = YandexOfferTracker.transition(idle, true, false, 4_000L)
        assertEquals(1L, first.generation)
        assertEquals(first, update)
        assertEquals(2L, second.generation)
        assertTrue(second.showing)
    }

    @Test fun onOrderNotificationEndsOfferButAllowsLiveOrderEnrichment() {
        assertTrue(YandexOfferTracker.isIdleStatus(payload("Яндекс Про", "На заказе")))
        assertTrue(YandexOfferTracker.isInProgressStatus(payload("Яндекс Про", "На заказе")))
        assertFalse(YandexOfferTracker.isInProgressStatus(payload("Яндекс Про", "На линии")))
        assertFalse(YandexOfferTracker.shouldClearEnrichment(payload("Яндекс Про", "На заказе"), true, true))
        assertFalse(YandexOfferTracker.shouldClearEnrichment(payload("Яндекс Про", "Занят"), true, false))
        assertTrue(YandexOfferTracker.shouldClearEnrichment(payload("Яндекс Про", "На линии"), true, true))
        assertTrue(YandexOfferTracker.shouldClearEnrichment(payload("Заказ отменён"), true, false))
        assertFalse(YandexOrderDetector.detect(payload("Яндекс Про", "На заказе")).isOrder)
    }

    @Test fun repeatedOfferWithoutStatusIsNotRedisplayed() {
        val first = YandexOfferTracker.transition(YandexOfferState(), true, false, 1_000L)
        val repeat = YandexOfferTracker.transition(first, true, false, 20_000L)
        assertEquals(first, repeat)
        val previous = IncomingOrderKey("local_1", null, "driver-1", null, null, "yandex_notification", 1_000L)
        val duplicate = previous.copy(time = 200_000L)
        assertEquals("same-event", IncomingOrderDeduplicator.decide(listOf(previous), duplicate).reason)
    }

    @Test fun sameNotificationKeyKeepsEventIdAcrossUpdates() {
        val first = payload("Новый заказ", "350 ₽")
        val updated = first.copy(postedAt = 999_999L, text = "350 ₽ · До клиента 2 км")
        assertEquals(IncomingOrderDeduplicator.eventId(first), IncomingOrderDeduplicator.eventId(updated))
    }

    @Test fun localThenFcmIsLinkedOnlyWithSameDriverPriceAndPickup() {
        val local = IncomingOrderKey("local", null, "driver-1", "350", "ул. Манаса 45", "yandex_notification", 1_000L)
        val fcm = IncomingOrderKey("fcm", "order-123", "driver-1", "350.0", "ул. Манаса 45", "fleet_api", 4_000L)
        assertEquals("linked-local-to-order", IncomingOrderDeduplicator.decide(listOf(local), fcm).reason)
        assertFalse(IncomingOrderDeduplicator.decide(listOf(local), fcm).accepted)
        assertTrue(IncomingOrderDeduplicator.decide(listOf(local), fcm.copy(pickup = "ул. Киевская 10")).accepted)
        assertTrue(IncomingOrderDeduplicator.decide(listOf(local), fcm.copy(price = "360")).accepted)
        assertTrue(IncomingOrderDeduplicator.decide(listOf(local), fcm.copy(driverId = "driver-2")).accepted)
    }
}
