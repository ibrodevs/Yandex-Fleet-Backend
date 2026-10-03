package kg.fleethub.driver_app.yandex

import org.junit.Assert.*
import org.junit.Test

class YandexCardParserTest {
    @Test fun titleOnlyOfferOpensWithoutInventingFields() {
        val card = YandexCardParser.parse(listOf("Яндекс Про", "Новый заказ"))
        assertTrue(card.offerVisible)
        assertNull(card.tariff)
        assertNull(card.price)
        assertNull(card.pickup)
    }

    @Test fun parsesVisibleLabeledCard() {
        val card = YandexCardParser.parse(listOf(
            "Новый заказ", "Тариф", "Комфорт+", "Тип заказа: Поездка",
            "Время в пути", "~40 мин", "1\u00a0564 ₽", "Оплата: безнал",
            "Откуда", "ул. Манаса, 45", "Куда", "проспект Чуй, 120",
            "Принять",
        ))
        assertTrue(card.offerVisible)
        assertEquals("Комфорт+", card.tariff)
        assertEquals("Поездка", card.orderType)
        assertEquals("40", card.durationMinutes)
        assertEquals("1564", card.price)
        assertEquals("RUB", card.currency)
        assertEquals("card", card.payment)
        assertEquals("ул. Манаса, 45", card.pickup)
        assertEquals("проспект Чуй, 120", card.destination)
    }

    @Test fun partialCardCanBeEnrichedLater() {
        val first = YandexCardParser.parse(listOf("Новый заказ"))
        val later = YandexCardParser.parse(listOf("Принять заказ", "Цена 1564 ₽", "Куда: проспект Чуй, 120"))
        assertTrue(first.offerVisible)
        assertNull(first.price)
        assertTrue(later.offerVisible)
        assertEquals("1564", later.price)
        assertEquals("проспект Чуй, 120", later.destination)
    }

    @Test fun doesNotReadUnrelatedYandexScreenOrInferAddresses() {
        val status = YandexCardParser.parse(listOf("Яндекс Про", "На линии", "1564 ₽", "ул. Манаса, 45"))
        assertFalse(status.offerVisible)
        assertNull(status.price)
        val offer = YandexCardParser.parse(listOf("Новый заказ", "ул. Манаса, 45", "40 мин до клиента"))
        assertNull(offer.pickup)
        assertNull(offer.durationMinutes)
    }
}
