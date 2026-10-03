package kg.fleethub.driver_app.yandex

/** Fields exposed by the current Yandex Pro accessibility tree; absent values stay absent. */
data class YandexCardDetails(
    val offerVisible: Boolean,
    val tariff: String? = null,
    val orderType: String? = null,
    val price: String? = null,
    val currency: String? = null,
    val payment: String? = null,
    val durationMinutes: String? = null,
    val pickup: String? = null,
    val destination: String? = null,
) {
    fun fieldNames(): String = listOfNotNull(
        tariff?.let { "tariff" }, orderType?.let { "type" }, price?.let { "price" },
        payment?.let { "payment" }, durationMinutes?.let { "duration" },
        pickup?.let { "pickup" }, destination?.let { "destination" },
    ).joinToString(",").ifBlank { "none" }
}

object YandexCardParser {
    private val offer = Regex("^(?:новый\\s+заказ|заказ\\s+для вас|new\\s+(?:ride|order))$", RegexOption.IGNORE_CASE)
    private val accept = Regex("^(?:принять(?:\\s+заказ)?|взять заказ|пропустить|отклонить)$", RegexOption.IGNORE_CASE)
    private val price = Regex("(?<!\\d)(\\d[\\d\\s\u00a0\u202f]{0,8})\\s*(₽|руб\\.?|сом|KGS|RUB)", RegexOption.IGNORE_CASE)
    private val minutes = Regex("(?:~|≈)?\\s*(\\d{1,3})\\s*мин(?:ут[аы]?)?\\b", RegexOption.IGNORE_CASE)
    private val tariffName = Regex("^(?:эконом|комфорт\\+?|бизнес|премиум|детский|минивэн|грузовой)$", RegexOption.IGNORE_CASE)
    private val paymentName = Regex("^(?:безнал(?:ичный(?: расч[её]т)?)?|картой|карта|наличные|наличными|cash|card)$", RegexOption.IGNORE_CASE)
    private val typeName = Regex("^(?:поездка|доставка|курьер|грузовой заказ)$", RegexOption.IGNORE_CASE)
    private val pickupLabel = Regex("^(?:откуда|адрес подачи|подача|точка а)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val destinationLabel = Regex("^(?:куда|адрес назначения|пункт назначения|точка б)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val tariffLabel = Regex("^тариф\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val typeLabel = Regex("^тип\\s+(?:заказа|поездки)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val paymentLabel = Regex("^оплата\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val durationLabel = Regex("^(?:время(?:\\s+в пути)?|в пути|длительность)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val unsuitableAddress = Regex("^(?:принять|отклонить|пропустить|новый заказ|₽|руб|сом|KGS|RUB|\\d+\\s*мин)", RegexOption.IGNORE_CASE)

    fun parse(nodeTexts: List<String>): YandexCardDetails {
        val texts = nodeTexts.asSequence().flatMap { it.split('\n').asSequence() }
            .map { it.trim().replace(Regex("\\s+"), " ") }.filter { it.isNotBlank() }
            .distinct().take(500).toList()
        val routeLabeled = texts.any { pickupLabel.matches(it) } && texts.any { destinationLabel.matches(it) }
        val visible = texts.any { offer.matches(it) || accept.matches(it) } ||
            (routeLabeled && texts.any { price.containsMatchIn(it) })
        if (!visible) return YandexCardDetails(false)

        fun labeled(pattern: Regex, acceptValue: (String) -> Boolean = { it.isNotBlank() },
                    acceptNext: (String) -> Boolean = acceptValue): String? {
            for ((index, text) in texts.withIndex()) {
                val match = pattern.matchEntire(text) ?: continue
                val inline = match.groupValues[1].trim()
                if (acceptValue(inline)) return inline
                val next = texts.getOrNull(index + 1)?.trim().orEmpty()
                if (acceptNext(next)) return next
            }
            return null
        }

        fun address(value: String) = value.length in 3..180 &&
            !unsuitableAddress.containsMatchIn(value) &&
            !pickupLabel.matches(value) && !destinationLabel.matches(value) &&
            !tariffLabel.matches(value) && !paymentLabel.matches(value)

        val priceMatch = texts.asSequence().mapNotNull { price.find(it) }.firstOrNull()
        val rawCurrency = priceMatch?.groupValues?.get(2)?.lowercase()
        val payment = labeled(paymentLabel) { paymentName.matches(it) }
            ?: texts.firstOrNull { paymentName.matches(it) }
        val duration = labeled(durationLabel) { minutes.containsMatchIn(it) }
            ?.let { minutes.find(it)?.groupValues?.get(1) }
            ?: texts.firstOrNull {
                minutes.containsMatchIn(it) && !it.contains("до клиента", true) &&
                    !it.contains("подача", true) && !it.contains("ожидание", true)
            }?.let { minutes.find(it)?.groupValues?.get(1) }
        return YandexCardDetails(
            offerVisible = true,
            tariff = labeled(tariffLabel, { it.isNotBlank() && it.length < 50 }, { tariffName.matches(it) })
                ?: texts.firstOrNull { tariffName.matches(it) },
            orderType = labeled(typeLabel, { it.isNotBlank() && it.length < 50 }, { typeName.matches(it) })
                ?: texts.firstOrNull { typeName.matches(it) },
            price = priceMatch?.groupValues?.get(1)?.replace(Regex("[\\s\u00a0\u202f]"), ""),
            currency = when (rawCurrency) { "₽", "руб.", "руб", "rub" -> "RUB"; "сом", "kgs" -> "KGS"; else -> null },
            payment = when (payment?.lowercase()) {
                "картой", "карта", "card", "безналичный расчёт", "безналичный расчет", "безнал" -> "card"
                "наличные", "наличными", "cash" -> "cash"
                else -> payment
            },
            durationMinutes = duration,
            pickup = labeled(pickupLabel, ::address),
            destination = labeled(destinationLabel, ::address),
        )
    }
}
