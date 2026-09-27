package kg.fleethub.driver_app.overlay
import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import io.flutter.plugins.firebase.messaging.FlutterFirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kg.fleethub.driver_app.MainActivity
import org.json.JSONObject

class OrderMessagingService: FlutterFirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        val payload=message.data["payload"] ?: return
        try { val order=JSONObject(payload); Handler(Looper.getMainLooper()).post { OrderDelivery.deliver(this,order) } } catch (_: Exception) { }
    }
}
object OrderDelivery {
    fun openIntent(context: Context, order: JSONObject): Intent = Intent(context,MainActivity::class.java)
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        .apply { if(!order.optBoolean("is_test")) putExtra("order_id",order.optString("order_id")) }
    fun deliver(context: Context, order: JSONObject) {
        val prefs=OverlayPreferences(context)
        val settings=prefs.settings
        val id=order.optString("order_id")
        if(order.optString("driver_id") != prefs.store.getString("driver_id", null)) return
        if(!prefs.active || id.isEmpty() || !settings.optBoolean("notifications",true)) return
        val seen=prefs.store.getStringSet("seen",emptySet())!!.toMutableSet()
        val manager=OverlayManager.get(context)
        if(seen.contains(id)) { if(manager.currentId==id) manager.show(order); return }
        val notifications=context.getSystemService(NotificationManager::class.java)
        if(!notifications.areNotificationsEnabled()) return
        var shown=false
        if(prefs.driverMode && OrderOverlayService.instance!=null && settings.optBoolean("overlay_enabled",true) && Settings.canDrawOverlays(context) && order.optString("type")=="new_order") {
            try { manager.show(order); shown=true } catch (_: Exception) { }
        }
        // Always retain a tappable system notification, including overlay fallback.
        val sound=settings.optBoolean("sound",true)
        val vibrate=settings.optBoolean("vibration",true)
        val channelId="fleet_orders_${sound}_${vibrate}"
        val channel=NotificationChannel(channelId,"Заказы",NotificationManager.IMPORTANCE_HIGH)
        if(!sound) channel.setSound(null,null)
        channel.enableVibration(vibrate)
        notifications.createNotificationChannel(channel)
        val pending=PendingIntent.getActivity(context,id.hashCode(),openIntent(context,order),PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val title=if(order.optBoolean("is_test")) "ПРОВЕРКА ЭКРАНА · пример" else "Новый заказ"
        val body="${text(order,"tariff_title")} · ${text(order,"price")} ${text(order,"currency")}\n${text(order,"pickup")} → ${text(order,"destination") }"
        try {
            notifications.notify(id.hashCode(),Notification.Builder(context,channelId).setSmallIcon(android.R.drawable.ic_menu_directions).setContentTitle(title).setContentText(body).setStyle(Notification.BigTextStyle().bigText(body)).setContentIntent(pending).setAutoCancel(true).build())
            shown=true
        } catch (_: SecurityException) { }
        if(shown) { seen.add(id); prefs.store.edit().putStringSet("seen",seen.toList().takeLast(300).toSet()).apply() }
    }
    fun text(o: JSONObject,key: String): String = if(o.isNull(key)) "—" else o.optString(key).ifEmpty { "—" }
}
