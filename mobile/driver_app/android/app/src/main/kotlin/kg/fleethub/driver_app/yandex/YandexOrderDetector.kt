package kg.fleethub.driver_app.yandex

import java.util.Locale

data class YandexNotificationPayload(
    val packageName: String, val key: String, val postedAt: Long,
    val title: String, val text: String, val bigText: String, val subText: String,
    val category: String?
)

data class OrderDetectionResult(
    val isOrder: Boolean, val confidence: String,
    val price: String? = null, val currency: String? = null,
    val pickup: String? = null, val destination: String? = null
)

object YandexOrderDetector {
    private val offer = Regex("(?:нов(?:ый|ое|ая)\\s+заказ|заказ\\s+(?:для вас|доступен|поступил)|предложени[ея]\\s+заказа|new\\s+(?:ride|order)|ride\\s+request)", RegexOption.IGNORE_CASE)
    private val negative = Regex("(?:заказ\\s+(?:отмен[её]н|заверш[её]н)|истори[яи]\\s+заказов|баланс|выплат|новост|акци[яи]|смена\\s+завершена)", RegexOption.IGNORE_CASE)
    private val pricePattern = Regex("(\\d[\\d\\s]{0,7})\\s*(₽|сом|KGS|RUB)", RegexOption.IGNORE_CASE)

    fun detect(payload: YandexNotificationPayload): OrderDetectionResult {
        val joined = listOf(payload.title, payload.text, payload.bigText, payload.subText)
            .filter { it.isNotBlank() }.distinct().joinToString("\n")
        if (negative.containsMatchIn(joined) || !offer.containsMatchIn(joined))
            return OrderDetectionResult(false, "low")
        val price = pricePattern.find(joined)
        val route = joined.lines().map { it.trim() }.filter { it.isNotEmpty() }
        val address = route.firstOrNull { it.contains(Regex("\\d+\\s*[,/-]?\\s*[А-Яа-яA-Za-z]|(?:ул\\.|улица|проспект|мкр)", RegexOption.IGNORE_CASE)) && !offer.containsMatchIn(it) && !pricePattern.containsMatchIn(it) }
        // An offer phrase alone may occur in service messages. Require an independent detail.
        val confirmed = price != null || address != null
        return OrderDetectionResult(confirmed, if (confirmed) "high" else "low",
            price?.groupValues?.get(1)?.replace(" ", ""),
            price?.groupValues?.get(2)?.uppercase(Locale.ROOT), address)
    }
}
