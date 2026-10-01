package kg.fleethub.driver_app.yandex

import android.app.Notification
import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import kg.fleethub.driver_app.R
import kg.fleethub.driver_app.overlay.IncomingOrderPresenter
import kg.fleethub.driver_app.overlay.OverlayPreferences
import org.json.JSONObject

class YandexNotificationListenerService : NotificationListenerService() {
    companion object {
        @Volatile var connected = false
            private set
        fun hasAccess(context: Context): Boolean {
            val enabled = Settings.Secure.getString(context.contentResolver, "enabled_notification_listeners") ?: return false
            val expected = ComponentName(context, YandexNotificationListenerService::class.java)
            return enabled.split(':').any { ComponentName.unflattenFromString(it) == expected }
        }
    }

    override fun onListenerConnected() {
        connected = true
        MonitorLog.write(this, "INFO", "PERMISSION", "Notification listener connected")
        YandexDiagnostics.listener?.invoke(mapOf("event" to "monitor_status_changed"))
    }

    override fun onListenerDisconnected() {
        connected = false
        MonitorLog.write(this, "WARN", "PERMISSION", "Notification listener disconnected")
        YandexDiagnostics.listener?.invoke(mapOf("event" to "monitor_status_changed"))
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
            val id = IncomingOrderDeduplicator.eventId(payload)
            val debug = getSharedPreferences("yandex_monitor", Context.MODE_PRIVATE).getBoolean("debug", false)
            MonitorLog.write(this, "INFO", "YANDEX_NOTIFICATION", "Notification received package=${sbn.packageName} key_hash=${sbn.key.hashCode()} category=${n.category} timestamp=${sbn.postTime}", id)
            if (debug) MonitorLog.write(this, "DEBUG", "YANDEX_NOTIFICATION", "title=${payload.title} text=${payload.text} big_text=${payload.bigText} sub_text=${payload.subText} extras_keys=${extras.keySet().joinToString()}", id)
            val result = YandexOrderDetector.detect(payload)
            MonitorLog.write(this, "INFO", "ORDER_DETECTOR", "is_order=${result.isOrder} confidence=${result.confidence}", id)
            if (!result.isOrder) return
            val prefs = OverlayPreferences(this)
            if (prefs.store.getString("driver_id", null).isNullOrBlank() || !prefs.active || !prefs.settings.optBoolean("notifications", true)) {
                MonitorLog.write(this, "WARN", "DEDUP", "Order ignored: no active linked driver or notifications disabled", id)
                return
            }
            val order = JSONObject().put("type", "incoming_order").put("source", "yandex_notification")
                .put("event_id", id).put("price", result.price).put("currency", result.currency)
                .put("pickup", result.pickup).put("destination", result.destination)
                .put("detected_at", System.currentTimeMillis())
            IncomingOrderPresenter.show(this, order)
        } catch (e: Exception) {
            MonitorLog.write(this, "ERROR", "YANDEX_NOTIFICATION", "Processing failed: ${e.javaClass.simpleName}")
        }
    }

    private fun allowed(name: String): Boolean = resources.getStringArray(R.array.yandex_pro_packages).contains(name)
}
