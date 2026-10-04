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
        assertEquals("cashless", card.payment)
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
        assertEquals("1.9", card.pickupDistanceKm)
        assertNull(card.distanceKm)
        assertNull(card.durationMinutes)
        assertNull(card.price)
        assertNull(card.payment)
        assertEquals("улица Блюхера, 15, подъезд 2", card.pickup)
        assertEquals("улица Куйбышева, 21", card.destination)
    }

    @Test fun preservesPaymentVariantsWithoutCollapsingPrepaymentIntoCard() {
        val methods = mapOf(
            "Наличные" to "cash", "Карта" to "card", "Безнал" to "cashless",
            "Корпоративный" to "corp", "Предоплата" to "prepaid",
            "Внутренний" to "internal", "Другое" to "other",
        )
        for ((visible, expected) in methods) {
            val card = YandexCardParser.parse(listOf("Новый заказ", "Оплата: $visible"))
            assertEquals(visible, expected, card.payment)
        }
    }

    @Test fun readsExplicitSomAndRublePricesButRejectsBonusBalanceAndCommission() {
        val som = YandexCardParser.parse(listOf(
            "Новый заказ", "Баланс 5 000 сом", "+130 ₽", "Комиссия 20 сом",
            "Цена поездки: 1 564,50 сом", "Расстояние поездки: 12,4 км",
        ))
        assertEquals("1564.50", som.price)
        assertEquals("KGS", som.currency)
        assertEquals("12.4", som.distanceKm)
        val rub = YandexCardParser.parse(listOf("Новый заказ", "Стоимость заказа 750 ₽"))
        assertEquals("750", rub.price)
        assertEquals("RUB", rub.currency)
        val unknown = YandexCardParser.parse(listOf("Новый заказ", "+130 ₽", "Ваш доход 322 ₽"))
        assertNull(unknown.price)
        assertNull(unknown.currency)
    }

    @Test fun mapLabelAndPickupMetricDoNotBecomePaymentOrTripDuration() {
        val card = YandexCardParser.parse(listOf(
            "Новый заказ", "Время в пути", "3,9 км · 6 мин", "Средняя подача", "Карта",
        ))
        assertNull(card.durationMinutes)
        assertNull(card.distanceKm)
        assertNull(card.payment)
        assertEquals("6", card.pickupEtaMinutes)
    }

    @Test fun activeYandexOrderCorrectsProvisionalPaymentAndReadsExplicitEstimates() {
        val offer = YandexCardParser.parse(listOf("Новый заказ", "2 км · 7 мин", "Средняя подача", "+130 ₽"))
        assertNull(offer.price)
        assertNull(offer.payment)
        assertNull(offer.durationMinutes)

        val active = YandexCardParser.parse(listOf(
            "На месте", "Ориентировочная стоимость поездки", "750 ₽",
            "До точки Б", "~28 мин", "Наличные", "Ваш доход 520 ₽",
        ), activeOrder = true)
        assertEquals("750", active.price)
        assertEquals("RUB", active.currency)
        assertTrue(active.priceEstimated)
        assertEquals("28", active.durationMinutes)
        assertEquals("cash", active.payment)
    }

    @Test fun activeScreenMustShowKnownOrderStageAndCardIsNotAStandalonePayment() {
        val unrelated = YandexCardParser.parse(listOf("На линии", "Наличные", "Цена 750 ₽"), activeOrder = true)
        assertFalse(unrelated.offerVisible)
        val active = YandexCardParser.parse(listOf("Поехали", "Карта", "Ваш доход 322 ₽"), activeOrder = true)
        assertTrue(active.offerVisible)
        assertNull(active.payment)
        assertNull(active.price)
    }
}
