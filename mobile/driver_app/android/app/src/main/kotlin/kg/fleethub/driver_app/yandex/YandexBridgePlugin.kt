package kg.fleethub.driver_app.yandex

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import io.flutter.embedding.engine.plugins.FlutterPlugin
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel

class YandexBridgePlugin : FlutterPlugin {
    private lateinit var methods: MethodChannel
    private lateinit var events: EventChannel
    override fun onAttachedToEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        val context = binding.applicationContext
        methods = MethodChannel(binding.binaryMessenger, "fleet/yandex/methods")
        events = EventChannel(binding.binaryMessenger, "fleet/yandex/events")
        events.setStreamHandler(object : EventChannel.StreamHandler {
            override fun onListen(arguments: Any?, sink: EventChannel.EventSink) {
                YandexDiagnostics.listener = { sink.success(it) }
                sink.success(mapOf("event" to "service_status_changed", "status" to YandexDiagnostics.status(context)))
            }
            override fun onCancel(arguments: Any?) { YandexDiagnostics.listener = null }
        })
        methods.setMethodCallHandler { call, result ->
            try {
                when (call.method) {
                    "getServiceStatus" -> result.success(YandexDiagnostics.status(context))
                    "isNotificationAccessGranted" -> result.success(YandexNotificationListenerService.hasAccess(context))
                    "openNotificationAccessSettings" -> {
                        open(context, Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS), Intent(Settings.ACTION_SETTINGS)); result.success(null)
                    }
                    "setMonitorDebug" -> {
                        context.getSharedPreferences("yandex_monitor", Context.MODE_PRIVATE).edit().putBoolean("debug", call.arguments == true).apply()
                        result.success(null)
                    }
                    "getMonitorLog" -> result.success(MonitorLog.read(context))
                    "clearMonitorLog" -> { MonitorLog.clear(context); result.success(null) }
                    "shareMonitorLog" -> {
                        val share = Intent(Intent.ACTION_SEND).setType("text/plain")
                            .putExtra(Intent.EXTRA_SUBJECT, "Yandex monitor diagnostics")
                            .putExtra(Intent.EXTRA_TEXT, MonitorLog.read(context))
                        context.startActivity(Intent.createChooser(share, "Сохранить логи мониторинга").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        result.success(null)
                    }
                    "isYandexInstalled" -> result.success(YandexDiagnostics.installed(context))
                    "isAccessibilityEnabled" -> result.success(YandexDiagnostics.enabled(context))
                    "canDrawOverlays" -> result.success(Settings.canDrawOverlays(context))
                    "openAccessibilitySettings" -> {
                        // Supported by AOSP Settings but not exposed as a public SDK constant.
                        // OEMs without this activity use the public accessibility settings action.
                        val detail = Intent("android.settings.ACCESSIBILITY_DETAILS_SETTINGS")
                            .putExtra(Intent.EXTRA_COMPONENT_NAME, ComponentName(context, YandexAccessibilityService::class.java).flattenToString())
                        open(context, detail, Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)); result.success(null)
                    }
                    "openOverlaySettings" -> {
                        open(context, Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:${context.packageName}")), Intent(Settings.ACTION_SETTINGS)); result.success(null)
                    }
                    "setDebugRecording" -> { YandexDiagnostics.setRecording(call.arguments == true); result.success(null) }
                    "getDebugLog" -> result.success(YandexDiagnostics.log())
                    "clearDebugLog" -> { YandexDiagnostics.clear(); result.success(null) }
                    else -> result.notImplemented()
                }
            } catch (e: Exception) { result.error("yandex_diagnostics", "Не удалось выполнить действие: ${e.javaClass.simpleName}", null) }
        }
    }
    private fun open(context: Context, intent: Intent, fallback: Intent) {
        try { context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
        catch (_: android.content.ActivityNotFoundException) { context.startActivity(fallback.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
    }
    override fun onDetachedFromEngine(binding: FlutterPlugin.FlutterPluginBinding) {
        methods.setMethodCallHandler(null); events.setStreamHandler(null); YandexDiagnostics.listener = null
    }
}
