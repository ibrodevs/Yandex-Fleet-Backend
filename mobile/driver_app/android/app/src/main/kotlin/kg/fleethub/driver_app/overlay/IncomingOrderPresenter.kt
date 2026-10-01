package kg.fleethub.driver_app.overlay

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import kg.fleethub.driver_app.MainActivity
import kg.fleethub.driver_app.R
import kg.fleethub.driver_app.yandex.IncomingOrderDeduplicator
import kg.fleethub.driver_app.yandex.MonitorLog
import kg.fleethub.driver_app.yandex.YandexDiagnostics
import org.json.JSONObject

object IncomingOrderPresenter {
    fun show(context: Context, order: JSONObject): Boolean {
        val id = order.optString("event_id")
        if (id.isBlank()) return false
        val orderId = order.optString("order_id").ifBlank { null }
        val price = order.optString("price").ifBlank { null }
        val pickup = order.optString("pickup").ifBlank { null }
        val manager = context.getSystemService(NotificationManager::class.java)
        if (!manager.areNotificationsEnabled()) {
            MonitorLog.write(context, "ERROR", "WIDGET", "Android notifications disabled", id, orderId)
            return false
        }
        if (!IncomingOrderDeduplicator.shouldShow(context, id, orderId, price, pickup)) {
            MonitorLog.write(context, "DEBUG", "DEDUP", "Duplicate ignored", id, orderId)
            return false
        }
        MonitorLog.write(context, "INFO", "WIDGET", "Incoming order notification requested", id, orderId)
        val channel = "yandex_incoming_orders"
        manager.createNotificationChannel(NotificationChannel(channel, "Входящие заказы Yandex", NotificationManager.IMPORTANCE_HIGH))
        val open = if (order.optString("source") == "yandex_notification") {
            context.resources.getStringArray(R.array.yandex_pro_packages).asSequence()
                .mapNotNull { context.packageManager.getLaunchIntentForPackage(it) }.firstOrNull()
        } else null
        val intent = (open ?: Intent(context, MainActivity::class.java)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        if (orderId != null && open == null) intent.putExtra("order_id", orderId)
        val pending = PendingIntent.getActivity(context, id.hashCode(), intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val parts = listOfNotNull(
            price?.let { it + " " + order.optString("currency") },
            pickup,
            order.optString("destination").ifBlank { null }
        )
        val body = parts.joinToString(" · ").ifBlank { "Откройте Yandex Pro, чтобы увидеть предложение" }
        return try {
            manager.notify(id.hashCode(), Notification.Builder(context, channel)
                .setSmallIcon(android.R.drawable.ic_menu_directions)
                .setContentTitle("Новый заказ Yandex")
                .setContentText(body).setStyle(Notification.BigTextStyle().bigText(body))
                .setContentIntent(pending).setAutoCancel(true).build())
            MonitorLog.write(context, "INFO", "WIDGET", "Incoming order notification displayed", id, orderId)
            val event = mapOf("event" to "incoming_order", "event_id" to id,
                "order_id" to orderId, "source" to order.optString("source"),
                "price" to price, "pickup_address" to pickup,
                "destination_address" to order.optString("destination").ifBlank { null },
                "detected_at" to order.optLong("detected_at"), "raw_data_available" to true)
            Handler(Looper.getMainLooper()).post { YandexDiagnostics.listener?.invoke(event) }
            true
        } catch (e: Exception) {
            IncomingOrderDeduplicator.forget(context, id)
            MonitorLog.write(context, "ERROR", "WIDGET", "Notification failed: ${e.javaClass.simpleName}", id, orderId)
            false
        }
    }
}
