package kg.fleethub.driver_app.yandex

import android.content.Context
import org.json.JSONObject
import java.security.MessageDigest

object IncomingOrderDeduplicator {
    private const val WINDOW_MS = 120_000L
    private fun hash(value: String): String = MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray()).take(12).joinToString("") { "%02x".format(it) }
    private fun normalizedPrice(value: String?) = value?.toDoubleOrNull()?.toLong()?.toString() ?: value.orEmpty()

    // A notification may be updated with new text without being a new offer.
    fun eventId(payload: YandexNotificationPayload): String = "yandex_evt_${hash("${payload.packageName}|${payload.key}|${payload.postedAt}")}"

    @Synchronized fun shouldShow(context: Context, eventId: String, orderId: String?, price: String?, pickup: String?): Boolean {
        val store = context.getSharedPreferences("incoming_order_dedup", Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        val entries = runCatching { JSONObject(store.getString("entries", "{}") ?: "{}") }.getOrDefault(JSONObject())
        val keys = entries.keys().asSequence().toList()
        for (key in keys) if (now - (entries.optJSONObject(key)?.optLong("time") ?: 0L) > 86_400_000L) entries.remove(key)
        val match = keys.firstOrNull { key ->
            val item = entries.optJSONObject(key) ?: return@firstOrNull false
            val sameOrder = !orderId.isNullOrBlank() && item.optString("order_id") == orderId
            val sameEvent = key == eventId
            val correlated = now - item.optLong("time") in 0..WINDOW_MS &&
                !price.isNullOrBlank() && normalizedPrice(price) == item.optString("price") &&
                !pickup.isNullOrBlank() && pickup.equals(item.optString("pickup"), ignoreCase = true)
            sameOrder || sameEvent || correlated
        }
        if (match != null) {
            if (!orderId.isNullOrBlank()) entries.optJSONObject(match)?.put("order_id", orderId)
            store.edit().putString("entries", entries.toString()).commit()
            return false
        }
        entries.put(eventId, JSONObject().put("time", now).put("order_id", orderId ?: "")
            .put("price", normalizedPrice(price)).put("pickup", pickup ?: ""))
        // Bounded persistent state, independent of Flutter lifecycle.
        while (entries.length() > 300) {
            val oldest = entries.keys().asSequence().minByOrNull { entries.optJSONObject(it)?.optLong("time") ?: 0L } ?: break
            entries.remove(oldest)
        }
        store.edit().putString("entries", entries.toString()).commit()
        return true
    }

    @Synchronized fun forget(context: Context, eventId: String) {
        val store = context.getSharedPreferences("incoming_order_dedup", Context.MODE_PRIVATE)
        val entries = runCatching { JSONObject(store.getString("entries", "{}") ?: "{}") }.getOrDefault(JSONObject())
        entries.remove(eventId)
        store.edit().putString("entries", entries.toString()).commit()
    }
}
