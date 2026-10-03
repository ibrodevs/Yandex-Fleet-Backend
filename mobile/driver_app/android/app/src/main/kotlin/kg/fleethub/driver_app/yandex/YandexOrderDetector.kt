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

/** Conservative rules: only high confidence is delivered in production. */
object YandexOrderDetector {
    private val offer = Regex("(?:нов(?:ый|ое|ая)\\s+заказ|заказ\\s+(?:для вас|доступен|поступил)|предложени[ея]\\s+заказа|new\\s+(?:ride|order)|ride\\s+request)", RegexOption.IGNORE_CASE)
    // Yandex Pro can publish the real incoming offer as only "Новый заказ",
    // without a price or address. An exact standalone phrase from its allowed
    // package is stronger evidence than a phrase inside a service message.
    private val standaloneOffer = Regex("^\\s*(?:новый\\s+заказ|заказ\\s+для вас|new\\s+(?:ride|order))\\s*[.!]?\\s*$", RegexOption.IGNORE_CASE)
    private val trip = Regex("(?:поездка|до клиента|trip|ride)", RegexOption.IGNORE_CASE)
    private val negative = Regex("(?:заказ\\s+(?:отмен[её]н|заверш[её]н)|поездка\\s+завершен[ао]|истори[яи]\\s+заказов|баланс|выплат|новост|акци[яи]|смена\\s+завершена)", RegexOption.IGNORE_CASE)
    private val pricePattern = Regex("(\\d[\\d\\s]{0,7})\\s*(₽|сом|KGS|RUB)", RegexOption.IGNORE_CASE)
    private val addressPattern = Regex("(?:ул\\.|улица|проспект|мкр|микрорайон|[А-Яа-яA-Za-z][А-Яа-яA-Za-z\\s.-]{2,}\\s+\\d+[А-Яа-яA-Za-z]?)", RegexOption.IGNORE_CASE)
    private val distance = Regex("\\d+(?:[.,]\\d+)?\\s*км", RegexOption.IGNORE_CASE)
    private val eta = Regex("\\d+\\s*мин", RegexOption.IGNORE_CASE)

    fun detect(payload: YandexNotificationPayload): OrderDetectionResult {
        val fields = listOf(payload.title, payload.text, payload.bigText, payload.subText)
        val joined = fields
            .filter { it.isNotBlank() }.distinct().joinToString("\n")
        if (negative.containsMatchIn(joined)) return OrderDetectionResult(false, "low")
        val exactOffer = fields.any { standaloneOffer.matches(it) }
        val price = pricePattern.find(joined)
        val address = joined.lines().map { it.trim() }.firstOrNull {
            addressPattern.containsMatchIn(it) && !offer.containsMatchIn(it) &&
                !pricePattern.containsMatchIn(it) && !negative.containsMatchIn(it) &&
                !distance.containsMatchIn(it) && !eta.containsMatchIn(it)
        }
        val details = listOf(price != null, address != null, distance.containsMatchIn(joined), eta.containsMatchIn(joined)).count { it }
        val confidence = when {
            exactOffer -> "high"
            offer.containsMatchIn(joined) && details > 0 -> "high"
            trip.containsMatchIn(joined) && details >= 2 -> "high"
            offer.containsMatchIn(joined) || trip.containsMatchIn(joined) && details > 0 -> "medium"
            else -> "low"
        }
        return OrderDetectionResult(confidence == "high", confidence,
            price?.groupValues?.get(1)?.replace(" ", ""),
            price?.groupValues?.get(2)?.uppercase(Locale.ROOT), address)
    }
}
