package kg.fleethub.driver_app.overlay

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kg.fleethub.driver_app.MainActivity
import kg.fleethub.driver_app.R
import kg.fleethub.driver_app.yandex.IncomingOrderDeduplicator
import kg.fleethub.driver_app.yandex.IncomingOrderKey
import kg.fleethub.driver_app.yandex.MonitorLog
import kg.fleethub.driver_app.yandex.YandexDiagnostics
import org.json.JSONObject

class OrderMessagingService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        MonitorLog.write(this, "INFO", "FCM", "FCM received message_id_hash=${message.messageId?.hashCode()}")
        val payload = message.data["payload"]
        if (payload.isNullOrBlank()) {
            MonitorLog.write(this, "ERROR", "FCM", "Missing payload")
            return
        }
        try {
            val order = JSONObject(payload)
            if (order.optString("source").isBlank()) order.put("source", "fcm")
            MonitorLog.write(this, "INFO", "FCM", "Order payload parsed source=${order.optString("source")}",
                order.optString("event_id"), order.optString("order_id"))
            Handler(Looper.getMainLooper()).post {
                try { OrderDelivery.deliver(this, order) }
                catch (e: Exception) { MonitorLog.write(this, "ERROR", "FCM", "Delivery failed: ${e.javaClass.simpleName}") }
            }
        } catch (e: Exception) {
            MonitorLog.write(this, "ERROR", "FCM", "Invalid JSON: ${e.javaClass.simpleName}")
        }
    }
}

/** Shared native delivery path for FCM and Yandex Pro notifications. */
object OrderDelivery {
    fun openIntent(context: Context, order: JSONObject): Intent {
        val isLocal = order.optString("source") == "yandex_notification"
        val yandex = if (isLocal) context.resources.getStringArray(R.array.yandex_pro_packages)
            .asSequence().mapNotNull { context.packageManager.getLaunchIntentForPackage(it) }.firstOrNull() else null
        return (yandex ?: Intent(context, MainActivity::class.java))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .apply {
                val id = value(order, "order_id")
                if (!order.optBoolean("is_test") && id != null && yandex == null) putExtra("order_id", id)
            }
    }

    fun notificationsAllowed(context: Context): Boolean {
        return try {
            val manager = context.getSystemService(NotificationManager::class.java)
            val runtime = Build.VERSION.SDK_INT < 33 ||
                context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
            runtime && manager.areNotificationsEnabled()
        } catch (_: SecurityException) { false }
    }

    fun deliver(context: Context, order: JSONObject) {
        val prefs = OverlayPreferences(context)
        val source = order.optString("source").ifBlank { if (order.optBoolean("is_test")) "test" else "fcm" }
        val orderId = value(order, "order_id")
        val deliveryId = orderId ?: value(order, "event_id")
        val eventId = value(order, "event_id") ?: deliveryId
        val savedDriver = prefs.store.getString("driver_id", null)
        val incomingDriver = value(order, "driver_id")
        MonitorLog.write(context, "INFO", "ORDER_DELIVERY", "Delivery started source=$source", eventId, orderId)
        if (savedDriver.isNullOrBlank() || incomingDriver != savedDriver) {
            MonitorLog.write(context, "ERROR", "ORDER_DELIVERY", "Driver mismatch or no linked driver source=$source", eventId, orderId)
            return
        }
        if (deliveryId == null || eventId == null) {
            MonitorLog.write(context, "ERROR", "ORDER_DELIVERY", "Missing order_id and event_id source=$source")
            return
        }
        if (!prefs.active || !prefs.settings.optBoolean("notifications", true)) {
            MonitorLog.write(context, "WARN", "ORDER_DELIVERY", "Monitoring inactive or notifications disabled source=$source", eventId, orderId)
            return
        }
        if (order.optString("type") != "new_order" && !order.optBoolean("is_test")) {
            MonitorLog.write(context, "WARN", "ORDER_DELIVERY", "Unsupported event type source=$source", eventId, orderId)
            return
        }
        val seen = prefs.store.getStringSet("seen", emptySet()).orEmpty().toMutableSet()
        if (source != "yandex_notification" && deliveryId in seen) {
            MonitorLog.write(context, "DEBUG", "DEDUP", "duplicate-$source-ignored source=$source reason=seen", eventId, orderId)
            return
        }
        var reserved = false
        if (!order.optBoolean("is_test")) {
            try {
                val decision = IncomingOrderDeduplicator.reserve(context, IncomingOrderKey(
                    eventId, orderId, savedDriver, value(order, "price"),
                    value(order, "pickup"), source, System.currentTimeMillis()))
                MonitorLog.write(context, "DEBUG", "DEDUP", "${decision.reason} source=$source", eventId, orderId)
                if (!decision.accepted) return
                reserved = true
            } catch (e: Exception) {
                MonitorLog.write(context, "ERROR", "DEDUP", "Dedup failed: ${e.javaClass.simpleName} source=$source", eventId, orderId)
                return
            }
        }

        val settings = prefs.settings
        val permission = try { Settings.canDrawOverlays(context) }
            catch (e: SecurityException) {
                MonitorLog.write(context, "ERROR", "OVERLAY", "Overlay permission check failed: SecurityException source=$source", eventId, orderId)
                false
            }
        val overlayEnabled = settings.optBoolean("overlay_enabled", true)
        var serviceAvailable = OrderOverlayService.instance != null
        if (prefs.driverMode && overlayEnabled && permission && !serviceAvailable) {
            try {
                context.startForegroundService(Intent(context, OrderOverlayService::class.java))
                MonitorLog.write(context, "INFO", "OVERLAY", "Overlay service start requested source=$source", eventId, orderId)
            } catch (e: Exception) {
                MonitorLog.write(context, "ERROR", "OVERLAY", "Service start failed: ${e.javaClass.simpleName} source=$source", eventId, orderId)
            }
        }
        serviceAvailable = OrderOverlayService.instance != null
        MonitorLog.write(context, "DEBUG", "OVERLAY",
            "driverMode=${prefs.driverMode} active=${prefs.active} overlay_enabled=$overlayEnabled overlay_permission=$permission service_running=$serviceAvailable source=$source",
            eventId, orderId)
        var shown = false
        if (prefs.driverMode && overlayEnabled && permission) {
            try {
                MonitorLog.write(context, "INFO", "OVERLAY", "Overlay show requested source=$source", eventId, orderId)
                OverlayManager.get(context).show(order)
                shown = true
                MonitorLog.write(context, "INFO", "OVERLAY", "Overlay shown source=$source", eventId, orderId)
            } catch (e: Exception) {
                MonitorLog.write(context, "ERROR", "OVERLAY", "Overlay show failed: ${e.javaClass.simpleName} source=$source", eventId, orderId)
            }
        }
        if (!shown) {
            MonitorLog.write(context, "WARN", "OVERLAY", "Overlay unavailable, using notification fallback source=$source", eventId, orderId)
            shown = showFallback(context, order, deliveryId, eventId, orderId, source, settings)
        }
        if (shown) {
            if (source != "yandex_notification") {
                seen.add(deliveryId)
                prefs.store.edit().putStringSet("seen", seen.toList().takeLast(300).toSet()).apply()
            }
            runCatching {
                YandexDiagnostics.listener?.invoke(mapOf("event" to "incoming_order", "source" to source,
                    "event_id" to eventId, "order_id" to orderId, "price" to value(order, "price"),
                    "pickup_address" to value(order, "pickup")))
            }.onFailure { MonitorLog.write(context, "ERROR", "FLUTTER", "EventChannel delivery failed: ${it.javaClass.simpleName}", eventId, orderId) }
        } else if (reserved) {
            IncomingOrderDeduplicator.forget(context, eventId)
        }
    }

    private fun showFallback(context: Context, order: JSONObject, deliveryId: String, eventId: String,
                             orderId: String?, source: String, settings: JSONObject): Boolean {
        if (!notificationsAllowed(context)) {
            MonitorLog.write(context, "ERROR", "NOTIFICATION", "Fleet Hub notifications disabled source=$source", eventId, orderId)
            return false
        }
        return try {
            val manager = context.getSystemService(NotificationManager::class.java)
            val sound = settings.optBoolean("sound", true)
            val vibrate = settings.optBoolean("vibration", true)
            val channelId = "fleet_orders_${sound}_${vibrate}"
            val channel = NotificationChannel(channelId, "Заказы", NotificationManager.IMPORTANCE_HIGH)
            if (!sound) channel.setSound(null, null)
            channel.enableVibration(vibrate)
            manager.createNotificationChannel(channel)
            val pending = PendingIntent.getActivity(context, deliveryId.hashCode(), openIntent(context, order),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            val body = listOfNotNull(value(order, "tariff_title"),
                value(order, "price")?.let { price -> listOfNotNull(price, value(order, "currency")).joinToString(" ") },
                value(order, "pickup"), value(order, "destination"))
                .joinToString(" · ").ifBlank { "Откройте приложение для деталей заказа" }
            val title = if (order.optBoolean("is_test")) "ПРОВЕРКА ЭКРАНА · пример" else "Новый заказ"
            manager.notify(deliveryId.hashCode(), Notification.Builder(context, channelId)
                .setSmallIcon(android.R.drawable.ic_menu_directions).setContentTitle(title)
                .setContentText(body).setStyle(Notification.BigTextStyle().bigText(body))
                .setContentIntent(pending).setAutoCancel(true).build())
            MonitorLog.write(context, "INFO", "NOTIFICATION", "Fallback notification shown source=$source", eventId, orderId)
            true
        } catch (e: Exception) {
            MonitorLog.write(context, "ERROR", "NOTIFICATION", "Fallback failed: ${e.javaClass.simpleName} source=$source", eventId, orderId)
            false
        }
    }

    fun value(o: JSONObject, key: String): String? = if (o.isNull(key)) null else o.optString(key).ifBlank { null }
    fun text(o: JSONObject, key: String): String = value(o, key) ?: "—"
}
