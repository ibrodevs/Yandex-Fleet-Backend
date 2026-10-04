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
    val distanceKm: String? = null,
    val pickupEtaMinutes: String? = null,
    val pickupDistanceKm: String? = null,
    val pickup: String? = null,
    val destination: String? = null,
    val priceCandidates: Int = 0,
    val routeLabels: Int = 0,
) {
    fun fieldNames(): String = listOfNotNull(
        tariff?.let { "tariff" }, orderType?.let { "type" }, price?.let { "price" },
        payment?.let { "payment" }, durationMinutes?.let { "duration" },
        distanceKm?.let { "distance" }, pickupDistanceKm?.let { "pickup_distance" },
        pickupEtaMinutes?.let { "pickup_eta" },
        pickup?.let { "pickup" }, destination?.let { "destination" },
    ).joinToString(",").ifBlank { "none" }
}

object YandexCardParser {
    private val offer = Regex("^(?:новый\\s+заказ|заказ\\s+для вас|new\\s+(?:ride|order))$", RegexOption.IGNORE_CASE)
    private val accept = Regex("^(?:принять(?:\\s+заказ)?|взять заказ|пропустить(?:\\s+приоритет\\s*-?\\d+)?|отклонить)$", RegexOption.IGNORE_CASE)
    private val price = Regex("(?<![\\d+\\-−])(\\d[\\d\\s\u00a0\u202f]{0,8}(?:[.,]\\d{1,2})?)\\s*(₽|руб\\.?|сом(?:ов)?|KGS|RUB|⃀)", RegexOption.IGNORE_CASE)
    private val priceLabel = Regex("^(?:цена(?:\\s+(?:поездки|заказа))?|стоимость(?:\\s+(?:поездки|заказа))?|итого|к оплате|сумма заказа|пассажир заплатит)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val unrelatedMoney = Regex("(?:доход|заработ|комисс|бонус|скидк|баланс|парк|повышенн|доплат|выплат)", RegexOption.IGNORE_CASE)
    private val minutes = Regex("(?:~|≈)?\\s*(\\d{1,3})\\s*мин(?:ут[аы]?)?(?![\\p{L}\\p{N}])", RegexOption.IGNORE_CASE)
    private val pickupEta = Regex("(\\d+(?:[.,]\\d+)?)\\s*км\\s*[·•]\\s*(\\d{1,3})\\s*мин(?:ут[аы]?)?(?![\\p{L}\\p{N}])", RegexOption.IGNORE_CASE)
    private val distance = Regex("(\\d+(?:[.,]\\d+)?)\\s*км(?![\\p{L}\\p{N}])", RegexOption.IGNORE_CASE)
    private val distanceLabel = Regex("^(?:расстояние(?: поездки| в пути)?|длина маршрута|в пути)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val tariffName = Regex("^(?:эконом|комфорт\\+?|бизнес|премиум|детский|минивэн|грузовой)$", RegexOption.IGNORE_CASE)
    private val paymentName = Regex("^(?:безнал(?:ичный(?: расч[её]т)?)?|безналичные|cashless|картой|карта|наличные|наличными|cash|card|корпоративн(?:ый|ая|ое)(?: сч[её]т)?|корп\\.?|corp|предоплата|предоплачено|prepaid|внутренний|internal|другое|other)$", RegexOption.IGNORE_CASE)
    private val typeName = Regex("^(?:поездка|доставка|курьер|грузовой заказ)$", RegexOption.IGNORE_CASE)
    private val pickupLabel = Regex("^(?:откуда|адрес подачи|подача|пункт отправления|пункт а|точка а)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val destinationLabel = Regex("^(?:куда|адрес назначения|пункт назначения|пункт прибытия|пункт б|точка б)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val markerA = Regex("^(?:[аa](?:\\s*[:：.]\\s*|\\s+)(.*)|[аa])$", RegexOption.IGNORE_CASE)
    private val markerB = Regex("^(?:б(?:\\s*[:：.]\\s*|\\s+)(.*)|б)$", RegexOption.IGNORE_CASE)
    private val tariffLabel = Regex("^тариф\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val typeLabel = Regex("^тип\\s+(?:заказа|поездки)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val paymentLabel = Regex("^(?:(?:способ|тип)\\s+оплаты|оплата)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val durationLabel = Regex("^(?:время\\s+(?:в пути|поездки)|в пути|длительность(?:\\s+поездки)?)\\s*[:：-]?\\s*(.*)$", RegexOption.IGNORE_CASE)
    private val unsuitableAddress = Regex("^(?:принять|отклонить|пропустить|новый заказ|₽|руб|сом|KGS|RUB|\\d+\\s*мин)", RegexOption.IGNORE_CASE)

    fun parse(nodeTexts: List<String>): YandexCardDetails {
        val texts = nodeTexts.asSequence().flatMap { it.split('\n').asSequence() }
            .map { it.trim().replace(Regex("\\s+"), " ") }.filter { it.isNotBlank() }
            // The map and the offer card can both contain A/B markers. Keep repeats:
            // the card's markers are the ones adjacent to actual address nodes.
            .take(500).toList()
        val routeLabeled = texts.any { pickupLabel.matches(it) } && texts.any { destinationLabel.matches(it) }

        fun labeled(pattern: Regex, acceptValue: (String) -> Boolean = { it.isNotBlank() },
                    acceptNext: (String) -> Boolean = acceptValue, lookAhead: Int = 1): String? {
            for ((index, text) in texts.withIndex()) {
                val match = pattern.matchEntire(text) ?: continue
                val inline = match.groupValues[1].trim()
                if (acceptValue(inline)) return inline
                for (offset in 1..lookAhead) {
                    val next = texts.getOrNull(index + offset)?.trim().orEmpty()
                    if (acceptNext(next)) return next
                }
            }
            return null
        }

        fun address(value: String) = value.length in 3..180 && value.any { it.isLetter() } &&
            !unsuitableAddress.containsMatchIn(value) &&
            !pickupLabel.matches(value) && !destinationLabel.matches(value) &&
            !markerA.matches(value) && !markerB.matches(value) &&
            !tariffLabel.matches(value) && !paymentLabel.matches(value) &&
            !typeLabel.matches(value) && !durationLabel.matches(value) &&
            !priceLabel.matches(value) && !offer.matches(value) && !accept.matches(value) &&
            !tariffName.matches(value) && !typeName.matches(value) && !paymentName.matches(value) &&
            !price.containsMatchIn(value) && !minutes.containsMatchIn(value) &&
            !value.equals("средняя подача", true) && !value.equals("пассажир", true)

        // Yandex Pro's offer card often has only A/B glyphs, with the map's A/B
        // glyphs earlier in the same tree. Require a nearby A-address-B-address
        // sequence so a map marker cannot become the pickup address.
        fun addressAfter(index: Int, oppositeMarker: Regex): Pair<Int, String>? {
            for (nextIndex in (index + 1)..minOf(index + 3, texts.lastIndex)) {
                val next = texts[nextIndex]
                if (oppositeMarker.matches(next)) break
                if (address(next)) return nextIndex to next
            }
            return null
        }
        val markerRoute = texts.withIndex().mapNotNull { (aIndex, aText) ->
            val a = markerA.matchEntire(aText) ?: return@mapNotNull null
            val (pickupIndex, pickup) = a.groupValues[1].takeIf(::address)?.let { aIndex to it }
                ?: addressAfter(aIndex, markerB)
                ?: return@mapNotNull null
            val bIndex = ((pickupIndex + 1)..minOf(pickupIndex + 3, texts.lastIndex))
                .firstOrNull { markerB.matches(texts[it]) } ?: return@mapNotNull null
            val b = markerB.matchEntire(texts[bIndex]) ?: return@mapNotNull null
            val destination = b.groupValues[1].takeIf(::address)
                ?: addressAfter(bIndex, markerA)?.second
                ?: return@mapNotNull null
            pickup to destination
        }.lastOrNull()
        val visible = texts.any { offer.matches(it) || accept.matches(it) } ||
            (routeLabeled && texts.any { price.containsMatchIn(it) }) ||
            (markerRoute != null && texts.any { tariffName.matches(it) } &&
                texts.any { it.equals("средняя подача", true) })
        if (!visible) return YandexCardDetails(false)

        // Other amounts on the screen can be earnings, bonuses or balances.
        // Never present the first bare amount as the passenger's trip price.
        val priceMatch = texts.withIndex().firstNotNullOfOrNull { (index, text) ->
            if (unrelatedMoney.containsMatchIn(text)) return@firstNotNullOfOrNull null
            val label = priceLabel.matchEntire(text) ?: return@firstNotNullOfOrNull null
            price.find(label.groupValues[1]) ?: run {
                var found: MatchResult? = null
                for (offset in 1..2) {
                    val next = texts.getOrNull(index + offset) ?: break
                    if (unrelatedMoney.containsMatchIn(next) || paymentLabel.matches(next) ||
                        durationLabel.matches(next) || pickupLabel.matches(next) ||
                        destinationLabel.matches(next)) break
                    found = price.find(next)
                    if (found != null) break
                }
                found
            }
        }
        val rawCurrency = priceMatch?.groupValues?.get(2)?.lowercase()
        val payment = labeled(paymentLabel, { paymentName.matches(it) })
        val duration = labeled(durationLabel,
            { minutes.containsMatchIn(it) && !pickupEta.containsMatchIn(it) },
            { minutes.containsMatchIn(it) && !pickupEta.containsMatchIn(it) &&
                !it.contains("до клиента", true) }, 2)
            ?.let { minutes.find(it)?.groupValues?.get(1) }
        val pickupEtaMinutes = texts.withIndex().firstNotNullOfOrNull { (index, text) ->
            val estimate = pickupEta.find(text) ?: return@firstNotNullOfOrNull null
            val pickupContext = (index + 1..minOf(index + 3, texts.lastIndex))
                .any { texts[it].contains("подача", true) }
            if (pickupContext) estimate.groupValues[2] else null
        }
        val pickupDistanceKm = texts.withIndex().firstNotNullOfOrNull { (index, text) ->
            val estimate = pickupEta.find(text) ?: return@firstNotNullOfOrNull null
            val pickupContext = (index + 1..minOf(index + 3, texts.lastIndex))
                .any { texts[it].contains("подача", true) }
            if (pickupContext) estimate.groupValues[1].replace(',', '.') else null
        }
        val distanceKm = labeled(distanceLabel, { distance.containsMatchIn(it) && !pickupEta.containsMatchIn(it) },
            { distance.containsMatchIn(it) && !pickupEta.containsMatchIn(it) }, 1)
            ?.let { distance.find(it)?.groupValues?.get(1)?.replace(',', '.') }
        return YandexCardDetails(
            offerVisible = true,
            tariff = labeled(tariffLabel, { it.isNotBlank() && it.length < 50 }, { tariffName.matches(it) })
                ?: texts.firstOrNull { tariffName.matches(it) },
            orderType = labeled(typeLabel, { it.isNotBlank() && it.length < 50 }, { typeName.matches(it) })
                ?: texts.firstOrNull { typeName.matches(it) },
            price = priceMatch?.groupValues?.get(1)?.replace(Regex("[\\s\u00a0\u202f]"), "")?.replace(',', '.'),
            currency = when (rawCurrency) { "₽", "руб.", "руб", "rub" -> "RUB"; "сом", "сомов", "kgs", "⃀" -> "KGS"; else -> null },
            payment = when (payment?.lowercase()) {
                "картой", "карта", "card" -> "card"
                "безналичный расчёт", "безналичный расчет", "безнал", "безналичные", "cashless" -> "cashless"
                "наличные", "наличными", "cash" -> "cash"
                "корпоративный", "корпоративная", "корпоративное", "корпоративный счёт", "корпоративный счет", "корп.", "корп", "corp" -> "corp"
                "предоплата", "предоплачено", "prepaid" -> "prepaid"
                "внутренний", "internal" -> "internal"
                "другое", "other" -> "other"
                else -> payment
            },
            durationMinutes = duration,
            distanceKm = distanceKm,
            pickupEtaMinutes = pickupEtaMinutes,
            pickupDistanceKm = pickupDistanceKm,
            pickup = labeled(pickupLabel, ::address, ::address, 2) ?: markerRoute?.first,
            destination = labeled(destinationLabel, ::address, ::address, 2) ?: markerRoute?.second,
            priceCandidates = texts.sumOf { price.findAll(it).count() },
            routeLabels = texts.count { pickupLabel.matches(it) || destinationLabel.matches(it) ||
                markerA.matches(it) || markerB.matches(it) },
        )
    }
}
