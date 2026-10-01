package kg.fleethub.driver_app.overlay

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kg.fleethub.driver_app.MainActivity
import kg.fleethub.driver_app.yandex.IncomingOrderDeduplicator
import kg.fleethub.driver_app.yandex.MonitorLog
import org.json.JSONObject

private const val TAG = "FleetFCM"

class OrderMessagingService : FirebaseMessagingService() {

    override fun onMessageReceived(message: RemoteMessage) {
        Log.d(TAG, "========================================")
        Log.d(TAG, "🔥 FCM RECEIVED")
        Log.d(TAG, "messageId=${message.messageId}")
        MonitorLog.write(this, "INFO", "FCM", "FCM received message_id=${message.messageId?.hashCode()}")

        val payload = message.data["payload"]

        if (payload == null) {
            Log.e(TAG, "❌ payload отсутствует")
            return
        }


        try {
            val order = JSONObject(payload)

            Log.d(TAG, "✅ JSON parsed")
            Log.d(TAG, "order_id=${order.optString("order_id")}")
            Log.d(TAG, "driver_id=${order.optString("driver_id")}")
            MonitorLog.write(this, "INFO", "FCM", "Order payload parsed", order.optString("event_id"), order.optString("order_id"))

            Handler(Looper.getMainLooper()).post {
                Log.d(TAG, "➡️ OrderDelivery.deliver()")
                OrderDelivery.deliver(this, order)
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Ошибка обработки payload", e)
            MonitorLog.write(this, "ERROR", "FCM", "Payload failed: ${e.javaClass.simpleName}")
        }
    }
}

object OrderDelivery {

    fun openIntent(context: Context, order: JSONObject): Intent =
        Intent(context, MainActivity::class.java)
            .addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_SINGLE_TOP
            )
            .apply {
                if (!order.optBoolean("is_test")) {
                    putExtra("order_id", order.optString("order_id"))
                }
            }

    fun deliver(context: Context, order: JSONObject) {
        Log.d(TAG, "========================================")
        Log.d(TAG, "🚕 OrderDelivery.deliver() START")

        val prefs = OverlayPreferences(context)
        val settings = prefs.settings

        val id = order.optString("order_id")
        val incomingDriver = order.optString("driver_id")
        val savedDriver = prefs.store.getString("driver_id", null)

        Log.d(TAG, "order_id=$id")
        Log.d(TAG, "incoming driver_id=$incomingDriver")
        Log.d(TAG, "saved driver_id=$savedDriver")
        Log.d(TAG, "prefs.active=${prefs.active}")
        Log.d(TAG, "prefs.driverMode=${prefs.driverMode}")
        Log.d(
            TAG,
            "service running=${OrderOverlayService.instance != null}"
        )
        Log.d(
            TAG,
            "overlay permission=${Settings.canDrawOverlays(context)}"
        )
        Log.d(
            TAG,
            "notifications setting=${settings.optBoolean("notifications", true)}"
        )
        Log.d(
            TAG,
            "overlay setting=${settings.optBoolean("overlay_enabled", true)}"
        )

        if (incomingDriver != savedDriver) {
            Log.e(
                TAG,
                "❌ DRIVER MISMATCH: incoming=$incomingDriver saved=$savedDriver"
            )
            return
        }

        Log.d(TAG, "✅ driver_id совпадает")

        if (!prefs.active) {
            Log.e(TAG, "❌ prefs.active = false")
            return
        }

        if (id.isEmpty()) {
            Log.e(TAG, "❌ order_id пустой")
            return
        }

        if (!settings.optBoolean("notifications", true)) {
            Log.e(TAG, "❌ notifications выключены в настройках")
            return
        }

        val seen = prefs.store
            .getStringSet("seen", emptySet())!!
            .toMutableSet()

        val manager = OverlayManager.get(context)

        if (seen.contains(id)) {
            Log.w(TAG, "⚠️ Заказ уже был получен: $id")
            return
        }

        val notifications =
            context.getSystemService(NotificationManager::class.java)

        Log.d(
            TAG,
            "Android notifications enabled=${notifications.areNotificationsEnabled()}"
        )

        if (!notifications.areNotificationsEnabled()) {
            Log.e(TAG, "❌ Android запретил уведомления")
            return
        }

        var dedupEventId: String? = null
        if (!order.optBoolean("is_test")) {
            val eventId = order.optString("event_id").ifBlank { "fleet_$id" }
            if (!IncomingOrderDeduplicator.shouldShow(context, eventId, id,
                    order.optString("price").ifBlank { null }, order.optString("pickup").ifBlank { null })) {
                MonitorLog.write(context, "DEBUG", "DEDUP", "Duplicate FCM ignored", eventId, id)
                return
            }
            dedupEventId = eventId
        }

        var shown = false

        val canShowOverlay =
            prefs.driverMode &&
                OrderOverlayService.instance != null &&
                settings.optBoolean("overlay_enabled", true) &&
                Settings.canDrawOverlays(context) &&
                order.optString("type") == "new_order"

        Log.d(TAG, "canShowOverlay=$canShowOverlay")

        if (!prefs.driverMode) {
            Log.w(TAG, "⚠️ Режим водителя выключен")
        }

        if (OrderOverlayService.instance == null) {
            Log.w(TAG, "⚠️ OrderOverlayService НЕ запущен")
        }

        if (!Settings.canDrawOverlays(context)) {
            Log.w(TAG, "⚠️ Нет SYSTEM_ALERT_WINDOW permission")
        }

        if (order.optString("type") != "new_order") {
            Log.w(
                TAG,
                "⚠️ Неверный type=${order.optString("type")}"
            )
        }

        if (canShowOverlay) {
            try {
                Log.d(TAG, "🚀 SHOWING OVERLAY")

                manager.show(order)

                shown = true

                Log.d(TAG, "✅ OVERLAY SHOWN")
            } catch (e: Exception) {
                Log.e(TAG, "❌ Ошибка manager.show()", e)
            }
        }

        val sound = settings.optBoolean("sound", true)
        val vibrate = settings.optBoolean("vibration", true)

        val channelId = "fleet_orders_${sound}_${vibrate}"

        val channel = NotificationChannel(
            channelId,
            "Заказы",
            NotificationManager.IMPORTANCE_HIGH
        )

        if (!sound) {
            channel.setSound(null, null)
        }

        channel.enableVibration(vibrate)

        notifications.createNotificationChannel(channel)

        val pending = PendingIntent.getActivity(
            context,
            id.hashCode(),
            openIntent(context, order),
            PendingIntent.FLAG_UPDATE_CURRENT or
                PendingIntent.FLAG_IMMUTABLE
        )

        val title =
            if (order.optBoolean("is_test")) {
                "ПРОВЕРКА ЭКРАНА · пример"
            } else {
                "Новый заказ"
            }

        val body = listOfNotNull(
            order.optString("tariff_title").ifBlank { null },
            order.optString("price").ifBlank { null }?.let { it + " " + order.optString("currency") },
            order.optString("pickup").ifBlank { null },
            order.optString("destination").ifBlank { null }
        ).joinToString(" · ").ifBlank { "Откройте приложение для деталей заказа" }

        try {
            Log.d(TAG, "🔔 Показываем системное уведомление")

            notifications.notify(
                id.hashCode(),
                Notification.Builder(context, channelId)
                    .setSmallIcon(android.R.drawable.ic_menu_directions)
                    .setContentTitle(title)
                    .setContentText(body)
                    .setStyle(
                        Notification.BigTextStyle().bigText(body)
                    )
                    .setContentIntent(pending)
                    .setAutoCancel(true)
                    .build()
            )

            shown = true

            Log.d(TAG, "✅ SYSTEM NOTIFICATION SHOWN")
        } catch (e: SecurityException) {
            Log.e(TAG, "❌ Notification SecurityException", e)
        }

        if (shown) {
            seen.add(id)

            prefs.store
                .edit()
                .putStringSet(
                    "seen",
                    seen.toList()
                        .takeLast(300)
                        .toSet()
                )
                .apply()

            Log.d(TAG, "✅ order_id сохранён в seen")
        } else {
            dedupEventId?.let { IncomingOrderDeduplicator.forget(context, it) }
        }

        Log.d(TAG, "🏁 OrderDelivery.deliver() END")
        Log.d(TAG, "========================================")
    }

    fun text(o: JSONObject, key: String): String =
        if (o.isNull(key)) {
            "—"
        } else {
            o.optString(key).ifEmpty { "—" }
        }
}
