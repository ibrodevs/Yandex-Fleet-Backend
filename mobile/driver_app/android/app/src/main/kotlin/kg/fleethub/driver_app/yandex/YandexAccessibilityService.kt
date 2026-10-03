package kg.fleethub.driver_app.yandex

import android.accessibilityservice.AccessibilityService
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONObject

class YandexAccessibilityService : AccessibilityService() {
    companion object {
        @Volatile private var instance: YandexAccessibilityService? = null
        fun requestCapture() { instance?.scheduleCapture(100) }
    }
    private val handler = Handler(Looper.getMainLooper())
    private var pending = false
    private var eventType = 0
    private var eventTime = 0L
    private val capture = Runnable {
        pending = false
        snapshot()
    }

    override fun onServiceConnected() {
        instance = this
        YandexDiagnostics.connection(true)
        if (YandexOfferEnrichment.hasPending(this)) scheduleCapture(100)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.packageName?.toString() != YandexDiagnostics.YANDEX_PRO_PACKAGE) return
        if (event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED &&
            event.eventType != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) return
        eventType = event.eventType
        eventTime = System.currentTimeMillis()
        scheduleCapture(300)
    }

    private fun scheduleCapture(delayMs: Long) {
        // A bounded trailing sample: continuous animations cannot postpone capture forever.
        if (!pending) { pending = true; handler.postDelayed(capture, delayMs) }
    }

    private fun snapshot() {
        val start = SystemClock.uptimeMillis()
        var count = 0
        var truncated = false
        val dump = StringBuilder()
        val texts = mutableListOf<String>()
        val root = runCatching { rootInActiveWindow }.getOrNull()
        val isYandex = runCatching { root?.packageName?.toString() == YandexDiagnostics.YANDEX_PRO_PACKAGE }.getOrDefault(false)
        val debug = YandexDiagnostics.recording && YandexDiagnostics.debugAvailable
        val enriching = YandexOfferEnrichment.hasPending(this)
        val collect = debug || enriching
        fun walk(node: AccessibilityNodeInfo, depth: Int) {
            try {
                if (count >= 500 || depth > 40 || SystemClock.uptimeMillis() - start > 80) { truncated = true; return }
                count++
                // Never record passwords or editable fields (including login credentials).
                if (node.isPassword || node.isEditable) return
                if (!node.isVisibleToUser) return
                val text = safeText(node.text)
                val description = safeText(node.contentDescription)
                if (enriching) {
                    text?.let { texts.add(it) }
                    if (description != text) description?.let { texts.add(it) }
                }
                if (debug) {
                    val bounds = Rect()
                    node.getBoundsInScreen(bounds)
                    dump.append(JSONObject(mapOf(
                        "depth" to depth, "text" to text,
                        "contentDescription" to description,
                        "viewId" to node.viewIdResourceName, "className" to node.className?.toString(),
                        "clickable" to node.isClickable, "enabled" to node.isEnabled,
                        "visible" to node.isVisibleToUser, "bounds" to bounds.toShortString(),
                    ))).append('\n')
                }
                for (i in 0 until node.childCount.coerceAtMost(500)) {
                    if (truncated) break
                    runCatching { node.getChild(i) }.getOrNull()?.let { child ->
                        try { walk(child, depth + 1) } finally { recycle(child) }
                    }
                }
            } catch (_: Exception) { truncated = true }
        }
        try { if (root != null && isYandex && collect) walk(root, 0) }
        finally { root?.let { recycle(it) } }
        if (enriching) YandexOfferEnrichment.onSnapshot(this, texts, count, isYandex)
        YandexDiagnostics.record(mapOf(
            "time" to eventTime, "capturedAt" to System.currentTimeMillis(),
            "eventType" to AccessibilityEvent.eventTypeToString(eventType),
            "package" to YandexDiagnostics.YANDEX_PRO_PACKAGE,
            "rootAvailable" to isYandex, "nodes" to count, "truncated" to truncated,
            "recording" to debug,
        ), dump.toString())
    }

    private fun safeText(value: CharSequence?): String? {
        val text = value?.toString() ?: return null
        if (Regex("(?i)(bearer|token|password|пароль|authorization|код подтверждения)").containsMatchIn(text)) return "[redacted]"
        return text.replace(Regex("[A-Za-z0-9_+/=-]{32,}"), "[redacted]").take(500)
    }

    @Suppress("DEPRECATION")
    private fun recycle(node: AccessibilityNodeInfo) { runCatching { node.recycle() } }
    override fun onInterrupt() {
        // Feedback interruption does not mean Android disconnected the service.
        handler.removeCallbacks(capture); pending = false
    }
    override fun onDestroy() { stopCapture(); super.onDestroy() }
    private fun stopCapture() {
        handler.removeCallbacks(capture); pending = false; instance = null; YandexDiagnostics.connection(false)
    }
}
