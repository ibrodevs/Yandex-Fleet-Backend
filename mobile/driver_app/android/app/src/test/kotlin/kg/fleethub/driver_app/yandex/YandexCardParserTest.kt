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
            "Время в пути", "~40 мин", "Цена: 1\u00a0564 ₽", "Оплата: безнал",
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

    @Test fun selectsTripPriceAndTimeInsteadOfFirstUnrelatedNumbers() {
        val card = YandexCardParser.parse(listOf(
            "Новый заказ", "Комфорт+", "6 мин", "Ваш доход 322 ₽",
            "Стоимость поездки", "750 ₽", "Время в пути", "~40 мин",
            "Способ оплаты", "Картой", "Откуда", "А", "ул. Манаса, 45",
            "Куда", "Б", "проспект Чуй, 120", "Принять заказ",
        ))
        assertEquals("750", card.price)
        assertEquals("40", card.durationMinutes)
        assertEquals("card", card.payment)
        assertEquals("ул. Манаса, 45", card.pickup)
        assertEquals("проспект Чуй, 120", card.destination)
        assertEquals(2, card.priceCandidates)
    }

    @Test fun hidesUnlabeledAmountAndPickupEtaRatherThanShowingWrongFare() {
        val card = YandexCardParser.parse(listOf("Новый заказ", "6 мин", "322 ₽", "Комфорт+"))
        assertNull(card.price)
        assertNull(card.durationMinutes)
        assertEquals("Комфорт+", card.tariff)
    }

    @Test fun readsOfferCardAddressesAfterRepeatedMapMarkers() {
        val card = YandexCardParser.parse(listOf(
            "Пропустить", "Приоритет -1", "А", "Б",
            "3,9 км · 6 мин", "Средняя подача", "Комфорт+",
            "А", "А", "улица Новгородцевой, 3",
            "Б", "Б", "Автолига, Водительский пр., 20, Екатеринбург",
            "Пассажир", "4.97", "+100 ₽",
        ))
        assertTrue(card.offerVisible)
        assertEquals("Комфорт+", card.tariff)
        assertEquals("улица Новгородцевой, 3", card.pickup)
        assertEquals("Автолига, Водительский пр., 20, Екатеринбург", card.destination)
        assertNull(card.price)
        assertNull(card.payment)
        assertNull(card.durationMinutes)
        assertEquals("6", card.pickupEtaMinutes)
    }

    @Test fun cardRemainsRecognizableWhenSkipButtonIsAbsentFromAccessibilityTree() {
        val card = YandexCardParser.parse(listOf(
            "3,9 км · 6 мин", "Средняя подача", "Комфорт+",
            "А", "улица Новгородцевой, 3",
            "Б", "Автолига, Водительский пр., 20, Екатеринбург",
            "+100 ₽",
        ))
        assertTrue(card.offerVisible)
        assertEquals("улица Новгородцевой, 3", card.pickup)
        assertEquals("Автолига, Водительский пр., 20, Екатеринбург", card.destination)
        assertNull(card.price)
        assertEquals("6", card.pickupEtaMinutes)
    }

    @Test fun separatesPickupEtaFromRideTimeOnCurrentOfferCard() {
        val card = YandexCardParser.parse(listOf(
            "Пропустить", "1,9 км · 5 мин", "Ближняя подача", "Комфорт",
            "А", "улица Блюхера, 15, подъезд 2",
            "Б", "улица Куйбышева, 21", "Пассажир", "+130 ₽",
        ))
        assertTrue(card.offerVisible)
        assertEquals("5", card.pickupEtaMinutes)
        assertNull(card.durationMinutes)
        assertNull(card.price)
        assertNull(card.payment)
        assertEquals("улица Блюхера, 15, подъезд 2", card.pickup)
        assertEquals("улица Куйбышева, 21", card.destination)
    }
}
