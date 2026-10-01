package kg.fleethub.driver_app.yandex

import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import android.view.accessibility.AccessibilityManager
import android.accessibilityservice.AccessibilityServiceInfo
import kg.fleethub.driver_app.BuildConfig
import kg.fleethub.driver_app.overlay.OrderDelivery
import kg.fleethub.driver_app.overlay.OrderOverlayService
import kg.fleethub.driver_app.overlay.OverlayPreferences

object YandexDiagnostics {
    const val YANDEX_PRO_PACKAGE = "ru.yandex.taximeter"
    val debugAvailable: Boolean get() = BuildConfig.DEBUG && BuildConfig.YANDEX_BRIDGE_DEBUG
    var recording = false
        private set
    var connected = false
    var lastEvent: Map<String, Any?>? = null
    private val entries = ArrayDeque<String>()
    private var size = 0
    var listener: ((Map<String, Any?>) -> Unit)? = null

    fun installed(context: Context): Boolean = context.resources.getStringArray(kg.fleethub.driver_app.R.array.yandex_pro_packages).any { name ->
        runCatching { context.packageManager.getPackageInfo(name, 0); true }.getOrDefault(false)
    }

    fun enabled(context: Context): Boolean {
        val manager = context.getSystemService(AccessibilityManager::class.java)
        val expected = ComponentName(context, YandexAccessibilityService::class.java)
        return manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
            .any { ComponentName(it.resolveInfo.serviceInfo.packageName, it.resolveInfo.serviceInfo.name) == expected }
    }

    fun status(context: Context): Map<String, Any?> = mapOf(
        "installed" to installed(context), "accessibility" to enabled(context),
        "notificationAccess" to YandexNotificationListenerService.hasAccess(context),
        "notificationListener" to YandexNotificationListenerService.connected,
        "fleetNotifications" to OrderDelivery.notificationsAllowed(context),
        "monitoringActive" to OverlayPreferences(context).active,
        "driverMode" to OverlayPreferences(context).driverMode,
        "overlayService" to (OrderOverlayService.instance != null),
        "fcmRegistered" to OverlayPreferences(context).store.getBoolean("fcm_registered", false),
        "monitorDebug" to context.getSharedPreferences("yandex_monitor", Context.MODE_PRIVATE).getBoolean("debug", false),
        "driverLinked" to (context.getSharedPreferences("fleet_overlay", Context.MODE_PRIVATE).getString("driver_id", null) != null),
        "overlay" to Settings.canDrawOverlays(context), "connected" to connected,
        "debugAvailable" to debugAvailable, "recording" to recording,
        "lastEvent" to lastEvent, "stage" to "diagnostics_only",
    )

    fun record(metadata: Map<String, Any?>, dump: String) {
        lastEvent = metadata
        if (recording && debugAvailable) {
            val entry = "${org.json.JSONObject(metadata)}\n$dump\n"
            entries.addLast(entry)
            size += entry.length
            while (size > 256_000 || entries.size > 30) size -= entries.removeFirst().length
        }
        listener?.invoke(mapOf("event" to "diagnostic_event", "lastEvent" to metadata))
    }

    fun setRecording(value: Boolean) { recording = value && debugAvailable; if (!recording) clear() }
    fun clear() { entries.clear(); size = 0; lastEvent = null }
    fun log(): String = if (debugAvailable) entries.joinToString("\n") else "Подробная диагностика отключена в release"
    fun connection(value: Boolean) {
        connected = value
        if (!value) { recording = false; clear() }
        listener?.invoke(mapOf("event" to "service_status_changed", "connected" to value))
    }
}
