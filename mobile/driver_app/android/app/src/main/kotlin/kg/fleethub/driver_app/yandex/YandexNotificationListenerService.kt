package kg.fleethub.driver_app.yandex

import android.app.Notification
import android.content.ComponentName
import android.content.Context
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import kg.fleethub.driver_app.R
import kg.fleethub.driver_app.overlay.OrderDelivery
import kg.fleethub.driver_app.overlay.OverlayPreferences
import org.json.JSONObject

class YandexNotificationListenerService : NotificationListenerService() {
    companion object {
        @Volatile var connected = false
            private set
        fun hasAccess(context: Context): Boolean {
            return try {
                val enabled = Settings.Secure.getString(context.contentResolver, "enabled_notification_listeners") ?: return false
                val expected = ComponentName(context, YandexNotificationListenerService::class.java)
                enabled.split(':').any { ComponentName.unflattenFromString(it) == expected }
            } catch (_: SecurityException) { false }
        }
    }

    override fun onListenerConnected() {
        connected = true
        MonitorLog.write(this, "INFO", "PERMISSION", "Notification listener connected")
        Handler(Looper.getMainLooper()).post { runCatching { YandexDiagnostics.listener?.invoke(mapOf("event" to "monitor_status_changed")) } }
    }

    override fun onListenerDisconnected() {
        connected = false
        MonitorLog.write(this, "WARN", "PERMISSION", "Notification listener disconnected")
        Handler(Looper.getMainLooper()).post { runCatching { YandexDiagnostics.listener?.invoke(mapOf("event" to "monitor_status_changed")) } }
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification?) {
        if (sbn != null && allowed(sbn.packageName))
            MonitorLog.write(this, "DEBUG", "YANDEX_NOTIFICATION", "Notification removed key=${sbn.key.hashCode()}")
    }

    override fun onDestroy() {
        connected = false
        super.onDestroy()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (sbn == null || !allowed(sbn.packageName)) return
        try {
            val n = sbn.notification
            val extras = n.extras
            val payload = YandexNotificationPayload(sbn.packageName, sbn.key, sbn.postTime,
                extras.getCharSequence(Notification.EXTRA_TITLE)?.toString().orEmpty(),
                extras.getCharSequence(Notification.EXTRA_TEXT)?.toString().orEmpty(),
                extras.getCharSequence(Notification.EXTRA_BIG_TEXT)?.toString().orEmpty(),
                extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString().orEmpty(), n.category)
            val result = YandexOrderDetector.detect(payload)
            val id = YandexOfferTracker.eventId(this, payload, result.isOrder)
            val debug = getSharedPreferences("yandex_monitor", Context.MODE_PRIVATE).getBoolean("debug", false)
            MonitorLog.write(this, "INFO", "YANDEX_NOTIFICATION", "Notification received package=${sbn.packageName} key_hash=${sbn.key.hashCode()} category=${n.category} timestamp=${sbn.postTime}", id)
            if (debug) MonitorLog.write(this, "DEBUG", "YANDEX_NOTIFICATION",
                "title=${payload.title.take(300)} text=${payload.text.take(300)} big_text=${payload.bigText.take(300)} sub_text=${payload.subText.take(300)} extras_keys=${extras.keySet().joinToString().take(300)}", id)
            MonitorLog.write(this, "INFO", "ORDER_DETECTOR", "is_order=${result.isOrder} confidence=${result.confidence} source=yandex_notification", id)
            if (!result.isOrder) {
                if (YandexOfferTracker.shouldClearEnrichment(payload,
                        YandexActionController.isTracking(id), YandexActionController.isIncoming(id))) {
                    YandexOfferEnrichment.clear(this)
                }
                if (result.confidence == "medium") MonitorLog.write(this, "DEBUG", "ORDER_IGNORED", "reason=insufficient_order_evidence", id)
                return
            }
            MonitorLog.write(this, "DEBUG", "ORDER_DETECTED", "source=yandex_notification confidence=${result.confidence}", id)
            val prefs = OverlayPreferences(this)
            val driverId = prefs.store.getString("driver_id", null)
            if (driverId.isNullOrBlank()) {
                MonitorLog.write(this, "WARN", "ORDER_DETECTOR", "Order detected but driver is not linked", id)
                return
            }
            MonitorLog.write(this, "INFO", "ORDER_DETECTOR", "Order confirmed source=yandex_notification", id)
            val order = JSONObject().put("type", "new_order").put("event_type", "incoming_order")
                .put("source", "yandex_notification").put("data_kind", "incoming_offer")
                .put("driver_id", driverId).put("order_id", "")
                .put("event_id", id).put("price", result.price).put("currency", result.currency)
                .put("pickup", result.pickup).put("destination", result.destination).put("tariff_title", JSONObject.NULL)
                .put("detected_at", System.currentTimeMillis())
            Handler(Looper.getMainLooper()).post {
                try {
                    OrderDelivery.deliver(this, order)
                    YandexOfferEnrichment.begin(this, order)
                }
                catch (e: Exception) { MonitorLog.write(this, "ERROR", "ORDER_DELIVERY", "Delivery failed: ${e.javaClass.simpleName}", id) }
            }
        } catch (e: Exception) {
            MonitorLog.write(this, "ERROR", "YANDEX_NOTIFICATION", "Processing failed: ${e.javaClass.simpleName}")
        }
    }

    private fun allowed(name: String): Boolean = resources.getStringArray(R.array.yandex_pro_packages).contains(name)
}
