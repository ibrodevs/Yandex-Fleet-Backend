package kg.fleethub.driver_app.yandex

import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.File
import java.time.Instant

object MonitorLog {
    private val secret = Regex("(?i)(bearer\\s+\\S+|authorization\\s*[:=]\\s*\\S+|(?:api[_ -]?key|api[_ -]?secret|password|token)\\s*[:=]\\s*\\S+)")
    private val phone = Regex("\\+\\d{9,15}")
    private val longValue = Regex("[A-Za-z0-9_+/=.\\-]{32,}")
    private fun safe(value: String) = value.replace(secret, "[redacted]")
        .replace(phone) { it.value.take(4) + "***" + it.value.takeLast(3) }
        .replace(longValue, "[redacted]").take(1000)

    @Synchronized fun write(context: Context, level: String, source: String, message: String, eventId: String? = null, orderId: String? = null) {
        try {
            val file = File(context.filesDir, "yandex_monitor.jsonl")
            val line = JSONObject().put("timestamp", Instant.now().toString()).put("level", level)
                .put("source", source).put("message", safe(message))
                .put("event_id", eventId).put("order_id", orderId).toString() + "\n"
            file.appendText(line)
            if (file.length() > 1_000_000) {
                val lines = file.readLines().takeLast(4000)
                file.writeText(lines.joinToString("\n", postfix = "\n"))
            }
            Handler(Looper.getMainLooper()).post { runCatching { YandexDiagnostics.listener?.invoke(mapOf("event" to "debug_log")) } }
        } catch (_: Exception) { /* Logging must never stop order delivery. */ }
    }

    fun read(context: Context): String {
        val prefs = context.getSharedPreferences("fleet_overlay", Context.MODE_PRIVATE)
        val file = File(context.filesDir, "yandex_monitor.jsonl")
        val packageInfo = context.packageManager.getPackageInfo(context.packageName, 0)
        val header = """=== YANDEX MONITOR DIAGNOSTICS ===
App version: ${packageInfo.versionName}
Build number: ${if (Build.VERSION.SDK_INT >= 28) packageInfo.longVersionCode else packageInfo.versionCode.toLong()}
Android: ${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})
Device: ${Build.MANUFACTURER} ${Build.MODEL}
Time: ${Instant.now()}
Notification access: ${YandexNotificationListenerService.hasAccess(context)}
Driver linked: ${prefs.getString("driver_id", null) != null}
FCM: token registration is managed by Flutter
Backend / Fleet API: check server worker logs

=== LAST EVENTS ===
""".trimIndent()
        return header + "\n" + if (file.exists()) file.readText() else ""
    }

    fun clear(context: Context) { File(context.filesDir, "yandex_monitor.jsonl").delete() }
}
