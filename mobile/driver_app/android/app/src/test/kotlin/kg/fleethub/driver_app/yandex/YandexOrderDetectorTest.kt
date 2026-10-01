package kg.fleethub.driver_app.yandex

import org.junit.Assert.*
import org.junit.Test

class YandexOrderDetectorTest {
    private fun payload(title: String, text: String = "") = YandexNotificationPayload(
        "ru.yandex.taximeter", "key", 123L, title, text, "", "", null)

    @Test fun confirmsOfferWithPriceWithoutInventingAddress() {
        val result = YandexOrderDetector.detect(payload("Новый заказ", "350 ₽"))
        assertTrue(result.isOrder)
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
        assertEquals("ул. Манаса 45", result.pickup)
        assertNull(result.price)
    }
}
