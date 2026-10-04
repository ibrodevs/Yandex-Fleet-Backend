package kg.fleethub.driver_app.yandex

import android.content.Context
import kg.fleethub.driver_app.overlay.OrderDelivery
import kg.fleethub.driver_app.overlay.OverlayManager
import kg.fleethub.driver_app.overlay.OverlayPreferences
import org.json.JSONObject

/** Connects an immediate notification overlay to later Yandex Pro screen data. */
object YandexOfferEnrichment {
    private const val WINDOW_MS = 120_000L
    private const val STORE = "yandex_offer_enrichment"
    private var lastSnapshotLogAt = 0L
    private var lastParseLogAt = 0L

    fun begin(context: Context, order: JSONObject) {
        val id = OrderDelivery.value(order, "event_id") ?: return
        val store = context.getSharedPreferences(STORE, Context.MODE_PRIVATE)
        if (store.getString("event_id", null) != id) {
            store.edit().putString("event_id", id).putString("order", order.toString())
                .putLong("started_at", System.currentTimeMillis()).apply()
            lastSnapshotLogAt = 0L
            lastParseLogAt = 0L
        } else {
            // A later update of the same Yandex notification may add details.
            val current = runCatching { JSONObject(store.getString("order", "{}") ?: "{}") }.getOrNull()
            if (current != null) {
                val changedFields = mutableListOf<String>()
                for (field in listOf("tariff_title", "price", "currency", "pickup", "destination")) {
                    val value = OrderDelivery.value(order, field)
                    if (value != null && value != OrderDelivery.value(current, field)) {
                        current.put(field, value)
                        changedFields.add(field)
                    }
                }
                if (changedFields.isNotEmpty()) {
                    store.edit().putString("order", current.toString()).apply()
                    IncomingOrderDeduplicator.updateDetails(context, id,
                        OrderDelivery.value(current, "price"), OrderDelivery.value(current, "pickup"))
                    runCatching { OverlayManager.get(context).update(current) }
                        .onSuccess { shown -> if (shown) MonitorLog.write(context, "DEBUG", "OVERLAY_UPDATED", "source=notification_update", id) }
                        .onFailure { MonitorLog.write(context, "ERROR", "OVERLAY", "notification_update_failed error=${it.javaClass.simpleName}", id) }
                    MonitorLog.write(context, "DEBUG", "ORDER_PARSED", "source=notification_update fields=${changedFields.joinToString(",")}", id)
                }
            }
        }
        if (!YandexDiagnostics.connected) {
            MonitorLog.write(context, "WARN", "ACCESSIBILITY_DATA", "capture_unavailable reason=service_not_connected", id)
        }
        YandexAccessibilityService.requestCapture()
    }

    fun clear(context: Context) {
        context.getSharedPreferences(STORE, Context.MODE_PRIVATE).edit().clear().apply()
    }

    fun hasPending(context: Context): Boolean = pending(context) != null

    private fun pending(context: Context): Pair<String, JSONObject>? {
        val store = context.getSharedPreferences(STORE, Context.MODE_PRIVATE)
        val id = store.getString("event_id", null) ?: return null
        val age = System.currentTimeMillis() - store.getLong("started_at", 0)
        if (age !in 0..WINDOW_MS) {
            clear(context)
            return null
        }
        val order = runCatching { JSONObject(store.getString("order", "{}") ?: "{}") }.getOrNull()
            ?: return null
        return id to order
    }

    fun onSnapshot(context: Context, texts: List<String>, nodeCount: Int, rootAvailable: Boolean) {
        val (id, order) = pending(context) ?: return
        if (!rootAvailable) {
            MonitorLog.write(context, "DEBUG", "ACCESSIBILITY_DATA", "root_unavailable reason=yandex_not_foreground", id)
            return
        }
        val details = try { YandexCardParser.parse(texts) }
        catch (e: Exception) {
            MonitorLog.write(context, "ERROR", "ACCESSIBILITY_DATA", "parse_failed error=${e.javaClass.simpleName}", id)
            return
        }
        val now = System.currentTimeMillis()
        if (now - lastSnapshotLogAt > 1_000) {
            MonitorLog.write(context, "DEBUG", "ACCESSIBILITY_DATA",
                "nodes=$nodeCount text_nodes=${texts.size} offer_visible=${details.offerVisible}", id)
            lastSnapshotLogAt = now
        }
        if (!details.offerVisible) return

        val updates = mapOf(
            "tariff_title" to details.tariff,
            "order_type" to details.orderType,
            "price" to details.price,
            "currency" to details.currency,
            "payment_method" to details.payment,
            "duration_minutes" to details.durationMinutes,
            "pickup_eta_minutes" to details.pickupEtaMinutes,
            "pickup" to details.pickup,
            "destination" to details.destination,
        )
        var changed = false
        for ((key, value) in updates) {
            if (value != null && value != OrderDelivery.value(order, key)) {
                order.put(key, value)
                changed = true
            }
        }
        if (changed || now - lastParseLogAt > 1_000) {
            val missing = listOfNotNull(
                if (details.price == null) "price" else null,
                if (details.payment == null) "payment" else null,
                if (details.durationMinutes == null) "duration" else null,
                if (details.pickupEtaMinutes == null) "pickup_eta" else null,
                if (details.pickup == null) "pickup" else null,
                if (details.destination == null) "destination" else null,
            ).joinToString(",").ifBlank { "none" }
            MonitorLog.write(context, "DEBUG", "ORDER_PARSED",
                "fields=${details.fieldNames()} missing=$missing changed=$changed price_candidates=${details.priceCandidates} route_labels=${details.routeLabels}", id)
            lastParseLogAt = now
        }
        if (!changed) return
        context.getSharedPreferences(STORE, Context.MODE_PRIVATE).edit().putString("order", order.toString()).apply()
        IncomingOrderDeduplicator.updateDetails(context, id,
            OrderDelivery.value(order, "price"), OrderDelivery.value(order, "pickup"))
        val prefs = OverlayPreferences(context)
        if (!prefs.active || !prefs.driverMode) {
            MonitorLog.write(context, "WARN", "OVERLAY", "update_skipped reason=monitoring_inactive", id)
            return
        }
        try {
            if (OverlayManager.get(context).update(order)) {
                MonitorLog.write(context, "INFO", "OVERLAY_UPDATED", "fields=${details.fieldNames()}", id)
            } else {
                MonitorLog.write(context, "DEBUG", "OVERLAY", "update_skipped reason=overlay_not_visible", id)
            }
        } catch (e: Exception) {
            MonitorLog.write(context, "ERROR", "OVERLAY", "update_failed error=${e.javaClass.simpleName}", id)
        }
    }
}
