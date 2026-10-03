package kg.fleethub.driver_app.yandex

import android.content.Context
import org.json.JSONObject
import java.security.MessageDigest
import java.math.BigDecimal

data class IncomingOrderKey(
    val eventId: String, val orderId: String?, val driverId: String,
    val price: String?, val pickup: String?, val source: String, val time: Long
)

data class DedupDecision(val accepted: Boolean, val reason: String, val matchedEventId: String? = null)

object IncomingOrderDeduplicator {
    private const val WINDOW_MS = 120_000L
    private const val RETENTION_MS = 86_400_000L
    private fun hash(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray()).take(12).joinToString("") { "%02x".format(it) }
    private fun normalizedPrice(value: String?) = runCatching {
        BigDecimal(value.orEmpty().trim().replace(',', '.')).stripTrailingZeros().toPlainString()
    }.getOrDefault(value.orEmpty().trim())
    private fun normalizedPickup(value: String?) = value.orEmpty().trim().lowercase().replace(Regex("\\s+"), " ")

    fun eventId(payload: YandexNotificationPayload): String {
        val fingerprint = if (payload.key.isNotBlank()) "${payload.packageName}|${payload.key}"
        else "${payload.packageName}|${payload.title}|${payload.text}|${payload.postedAt / 30_000L}"
        return "yandex_evt_${hash(fingerprint)}"
    }

    /** Pure decision function, also used by JVM tests. */
    fun decide(previous: List<IncomingOrderKey>, incoming: IncomingOrderKey): DedupDecision {
        for (item in previous) {
            if (item.driverId != incoming.driverId) continue
            if (item.eventId == incoming.eventId)
                return DedupDecision(false, "same-event", item.eventId)
            if (!incoming.orderId.isNullOrBlank() && item.orderId == incoming.orderId)
                return DedupDecision(false, "same-order", item.eventId)
            val crossSource = (item.source == "yandex_notification") != (incoming.source == "yandex_notification")
            val closeInTime = incoming.time - item.time in 0..WINDOW_MS
            val sameDetails = !incoming.price.isNullOrBlank() && !incoming.pickup.isNullOrBlank() &&
                normalizedPrice(incoming.price) == normalizedPrice(item.price) &&
                normalizedPickup(incoming.pickup) == normalizedPickup(item.pickup)
            if (crossSource && closeInTime && sameDetails)
                return DedupDecision(false, "linked-local-to-order", item.eventId)
        }
        return DedupDecision(true, "local-new")
    }

    @Synchronized fun reserve(context: Context, incoming: IncomingOrderKey): DedupDecision {
        val store = context.getSharedPreferences("incoming_order_dedup", Context.MODE_PRIVATE)
        val entries = runCatching { JSONObject(store.getString("entries", "{}") ?: "{}") }.getOrDefault(JSONObject())
        val previous = mutableListOf<IncomingOrderKey>()
        for (key in entries.keys().asSequence().toList()) {
            val item = entries.optJSONObject(key)
            if (item == null || incoming.time - item.optLong("time") > RETENTION_MS) { entries.remove(key); continue }
            previous += IncomingOrderKey(key, item.optString("order_id").ifBlank { null },
                item.optString("driver_id"), item.optString("price").ifBlank { null },
                item.optString("pickup").ifBlank { null }, item.optString("source"), item.optLong("time"))
        }
        val decision = decide(previous, incoming)
        if (!decision.accepted) {
            if (decision.reason == "linked-local-to-order" && !incoming.orderId.isNullOrBlank())
                entries.optJSONObject(decision.matchedEventId)?.put("order_id", incoming.orderId)
        } else {
            entries.put(incoming.eventId, JSONObject().put("time", incoming.time)
                .put("order_id", incoming.orderId ?: "").put("driver_id", incoming.driverId)
                .put("price", incoming.price ?: "").put("pickup", incoming.pickup ?: "")
                .put("source", incoming.source))
        }
        while (entries.length() > 300) {
            val oldest = entries.keys().asSequence().minByOrNull { entries.optJSONObject(it)?.optLong("time") ?: 0L } ?: break
            entries.remove(oldest)
        }
        store.edit().putString("entries", entries.toString()).commit()
        return decision
    }

    @Synchronized fun forget(context: Context, eventId: String) {
        val store = context.getSharedPreferences("incoming_order_dedup", Context.MODE_PRIVATE)
        val entries = runCatching { JSONObject(store.getString("entries", "{}") ?: "{}") }.getOrDefault(JSONObject())
        entries.remove(eventId)
        store.edit().putString("entries", entries.toString()).commit()
    }
}
