package kg.fleethub.driver_app.yandex

import org.junit.Assert.*
import org.junit.Test

class YandexOrderDetectorTest {
    private fun payload(title: String, text: String = "") = YandexNotificationPayload(
        "ru.yandex.taximeter", "key", 123L, title, text, "", "", null)

    @Test fun confirmsOfferWithPriceWithoutInventingAddress() {
        val result = YandexOrderDetector.detect(payload("Новый заказ", "350 ₽"))
        assertTrue(result.isOrder)
        assertEquals("high", result.confidence)
        assertEquals("350", result.price)
        assertEquals("₽", result.currency)
        assertNull(result.pickup)
        assertNull(result.destination)
    }

    @Test fun rejectsVagueOfferAndServiceMessages() {
        assertFalse(YandexOrderDetector.detect(payload("Новый заказ")).isOrder)
        assertFalse(YandexOrderDetector.detect(payload("Заказ отменён", "350 ₽")).isOrder)
        assertFalse(YandexOrderDetector.detect(payload("Новости сервиса", "350 ₽")).isOrder)
    }

    @Test fun acceptsAddressWithoutPrice() {
        val result = YandexOrderDetector.detect(payload("Заказ для вас", "ул. Манаса 45"))
        assertTrue(result.isOrder)
        assertEquals("high", result.confidence)
        assertEquals("ул. Манаса 45", result.pickup)
        assertNull(result.price)
    }

    @Test fun mediumOfferIsLoggedButNotDelivered() {
        val result = YandexOrderDetector.detect(payload("Новый заказ"))
        assertFalse(result.isOrder)
        assertEquals("medium", result.confidence)
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
