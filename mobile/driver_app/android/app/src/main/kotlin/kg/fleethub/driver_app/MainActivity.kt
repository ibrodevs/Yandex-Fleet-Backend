package kg.fleethub.driver_app

import android.content.Intent
import android.net.Uri
import android.provider.Settings
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import kg.fleethub.driver_app.overlay.*
import org.json.JSONObject

class MainActivity: FlutterActivity() {
    private var channel: MethodChannel? = null
    override fun configureFlutterEngine(engine: FlutterEngine) {
        super.configureFlutterEngine(engine)
        channel = MethodChannel(engine.dartExecutor.binaryMessenger, "fleet/overlay")
        channel!!.setMethodCallHandler { call, result ->
            try {
                val prefs = OverlayPreferences(this)
                when (call.method) {
                    "isOverlayPermissionGranted" -> result.success(Settings.canDrawOverlays(this))
                    "requestOverlayPermission" -> {
                        startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
                        result.success(null)
                    }
                    "setSession" -> { prefs.store.edit().putString("driver_id", call.arguments as? String).apply(); result.success(null) }
                    "setSettings" -> { prefs.settings = JSONObject(call.arguments as Map<*, *>); prefs.active = true; result.success(null) }
                    "getDriverMode" -> result.success(OrderOverlayService.instance != null && prefs.driverMode)
                    "setDriverMode" -> {
                        val enabled = call.arguments == true
                        if (enabled) { startForegroundService(Intent(this, OrderOverlayService::class.java)); prefs.driverMode = true }
                        else { prefs.driverMode = false; stopService(Intent(this, OrderOverlayService::class.java)) }
                        result.success(null)
                    }
                    "showTestOverlay" -> {
                        if (!Settings.canDrawOverlays(this)) { result.error("permission", "Разрешите показ поверх приложений", null) }
                        else {
                            OverlayManager.get(this).show(JSONObject().put("is_test",true).put("order_id","local-test").put("tariff_title","Входящий заказ · пример").put("price",380).put("currency","RUB").put("distance_km",12).put("duration_minutes",20))
                            result.success(null)
                        }
                    }
                    "showOrderOverlay" -> { OrderDelivery.deliver(this, JSONObject(call.arguments as Map<*, *>)); result.success(null) }
                    "hideOverlay" -> { OverlayManager.get(this).hide(); result.success(null) }
                    "clearSession" -> { getSystemService(android.app.NotificationManager::class.java).cancelAll(); prefs.clear(); OverlayManager.get(this).hide(); result.success(null) }
                    "initialOrder" -> { result.success(intent.getStringExtra("order_id")); intent.removeExtra("order_id") }
                    else -> result.notImplemented()
                }
            } catch (e: Exception) { result.error("native", e.javaClass.simpleName, null) }
        }
    }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        intent.getStringExtra("order_id")?.let { channel?.invokeMethod("openOrder", it); intent.removeExtra("order_id") }
    }
}
