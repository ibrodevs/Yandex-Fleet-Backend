package kg.fleethub.driver_app.yandex

import android.content.Context

data class YandexOfferState(
    val generation: Long = 0,
    val showing: Boolean = false,
    val startedAt: Long = 0,
)

/** Keeps one notification key stable during an offer, but separates later offers. */
object YandexOfferTracker {
    private const val MAX_OFFER_AGE_MS = 120_000L
    private val idleStatus = Regex(
        "^\\s*(?:на линии|на заказе|занят|заказ\\s+(?:отмен[её]н|принят|заверш[её]н)|поездка\\s+завершен[ао])\\s*[.!]?\\s*$",
        RegexOption.IGNORE_CASE,
    )

    fun transition(
        current: YandexOfferState,
        isOrder: Boolean,
        isIdleStatus: Boolean,
        at: Long,
    ): YandexOfferState = when {
        isOrder && (!current.showing || at - current.startedAt > MAX_OFFER_AGE_MS) ->
            YandexOfferState(current.generation + 1, true, at)
        isOrder -> current
        isIdleStatus -> current.copy(showing = false)
        else -> current
    }

    fun isIdleStatus(payload: YandexNotificationPayload): Boolean =
        listOf(payload.title, payload.text, payload.bigText, payload.subText)
            .any { idleStatus.matches(it) }

    /** These statuses close the offer but may start the same order's live trip. */
    fun isInProgressStatus(payload: YandexNotificationPayload): Boolean =
        listOf(payload.title, payload.text, payload.bigText, payload.subText).any {
            Regex("^\\s*(?:на заказе|заказ\\s+принят)\\s*[.!]?\\s*$", RegexOption.IGNORE_CASE).matches(it)
        }

    fun shouldClearEnrichment(payload: YandexNotificationPayload, tracking: Boolean,
                              incoming: Boolean): Boolean {
        if (!isIdleStatus(payload)) return false
        val finished = listOf(payload.title, payload.text, payload.bigText, payload.subText).any {
            Regex("^\\s*(?:заказ\\s+(?:отмен[её]н|заверш[её]н)|поездка\\s+завершен[ао])\\s*[.!]?\\s*$",
                RegexOption.IGNORE_CASE).matches(it)
        }
        return finished || !tracking || (incoming && !isInProgressStatus(payload))
    }

    @Synchronized
    fun eventId(context: Context, payload: YandexNotificationPayload, isOrder: Boolean): String {
        val base = IncomingOrderDeduplicator.eventId(payload)
        if (payload.key.isBlank()) return base
        val prefs = context.getSharedPreferences("yandex_offer_tracker", Context.MODE_PRIVATE)
        val current = YandexOfferState(
            prefs.getLong("$base.generation", 0),
            prefs.getBoolean("$base.showing", false),
            prefs.getLong("$base.started_at", 0),
        )
        val next = transition(
            current,
            isOrder,
            isIdleStatus(payload),
            payload.postedAt.takeIf { it > 0 } ?: System.currentTimeMillis(),
        )
        if (next != current) {
            prefs.edit().putLong("$base.generation", next.generation)
                .putBoolean("$base.showing", next.showing)
                .putLong("$base.started_at", next.startedAt).commit()
        }
        return if (next.generation > 0) "${base}_${next.generation}" else base
    }
}
