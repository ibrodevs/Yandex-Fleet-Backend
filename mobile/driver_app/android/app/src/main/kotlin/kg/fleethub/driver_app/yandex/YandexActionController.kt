package kg.fleethub.driver_app.yandex

import android.content.Context
import android.graphics.Rect
import android.os.SystemClock
import android.view.accessibility.AccessibilityNodeInfo
import kg.fleethub.driver_app.overlay.OverlayManager

enum class YandexStage { INCOMING, ACCEPTED, WAITING, RIDING, COMPLETED }
enum class YandexAction(val title: String) {
    ACCEPT("Принять"), ARRIVED("На месте"), START("Поехали"), FINISH("Завершить")
}

/** Exact screen evidence only. A requested click never advances the stage by itself. */
object YandexActionPolicy {
    private val complete = Regex("^(?:заказ|поездка)?\\s*заверш[её]н[ао]?\\s*[.!]?$", RegexOption.IGNORE_CASE)
    private val labels = mapOf(
        YandexAction.ACCEPT to Regex("^принять(?: заказ)?$", RegexOption.IGNORE_CASE),
        YandexAction.ARRIVED to Regex("^на месте$", RegexOption.IGNORE_CASE),
        YandexAction.START to Regex("^поехали$", RegexOption.IGNORE_CASE),
        YandexAction.FINISH to Regex("^завершить(?: поездку| заказ)?$", RegexOption.IGNORE_CASE),
    )

    fun actionFor(stage: YandexStage): YandexAction? = when (stage) {
        YandexStage.INCOMING -> YandexAction.ACCEPT
        YandexStage.ACCEPTED -> YandexAction.ARRIVED
        YandexStage.WAITING -> YandexAction.START
        YandexStage.RIDING -> YandexAction.FINISH
        YandexStage.COMPLETED -> null
    }

    fun matches(action: YandexAction, text: String?): Boolean =
        text != null && text.lines().any { labels.getValue(action).matches(it.trim()) }

    fun screenStage(texts: List<String>): YandexStage? {
        val normalized = texts.flatMap { it.lines() }.map(String::trim)
        if (normalized.any { complete.matches(it) }) return YandexStage.COMPLETED
        val matched = labels.filter { (action, pattern) ->
            normalized.any { pattern.matches(it) }
        }.keys
        if (matched.size != 1) return null
        return when (matched.single()) {
            YandexAction.ACCEPT -> YandexStage.INCOMING
            YandexAction.ARRIVED -> YandexStage.ACCEPTED
            YandexAction.START -> YandexStage.WAITING
            YandexAction.FINISH -> YandexStage.RIDING
        }
    }

    fun confirmsNext(current: YandexStage, observed: YandexStage?): Boolean =
        observed != null && observed.ordinal == current.ordinal + 1

    fun usableTarget(packageName: String?, visible: Boolean, enabled: Boolean,
                     clickable: Boolean, hasClickAction: Boolean, nonEmptyBounds: Boolean): Boolean =
        packageName == YandexDiagnostics.YANDEX_PRO_PACKAGE && visible && enabled &&
            clickable && hasClickAction && nonEmptyBounds

    fun usableGestureLabel(left: Int, top: Int, right: Int, bottom: Int,
                           windowLeft: Int, windowTop: Int, windowRight: Int, windowBottom: Int): Boolean {
        val windowHeight = windowBottom - windowTop
        return windowHeight > 0 && right - left >= 16 && bottom - top >= 12 &&
            bottom - top <= windowHeight / 5 && left >= windowLeft && top >= windowTop &&
            right <= windowRight && bottom <= windowBottom
    }

    fun usableClickBounds(left: Int, top: Int, right: Int, bottom: Int,
                          labelX: Int, labelY: Int, windowHeight: Int): Boolean =
        windowHeight > 0 && right > left && bottom > top &&
            bottom - top <= windowHeight / 4 && labelX in left until right && labelY in top until bottom

    fun usableSliderBounds(left: Int, top: Int, right: Int, bottom: Int,
                           labelX: Int, labelY: Int, windowLeft: Int, windowTop: Int,
                           windowRight: Int, windowBottom: Int): Boolean {
        val windowWidth = windowRight - windowLeft
        val windowHeight = windowBottom - windowTop
        val width = right - left
        val height = bottom - top
        return windowWidth > 0 && windowHeight > 0 &&
            width >= windowWidth * 35 / 100 && height in 24..(windowHeight / 7) &&
            left >= windowLeft && right <= windowRight && top >= windowTop + windowHeight / 2 &&
            bottom <= windowBottom && labelX in left until right && labelY in top until bottom &&
            labelX <= left + width * 65 / 100
    }
}

/** Only the accessibility service supplies a live Yandex Pro root to this controller. */
object YandexActionController {
    private const val CONFIRM_TIMEOUT_MS = 10_000L
    @Volatile private var eventId: String? = null
    @Volatile private var stage = YandexStage.INCOMING
    private var pending: YandexAction? = null
    private var pendingSince = 0L
    private var preferGesture = false

    fun start(context: Context, id: String) {
        if (eventId == id) return
        eventId = id
        stage = YandexStage.INCOMING
        pending = null
        preferGesture = false
        MonitorLog.write(context, "DEBUG", "YANDEX_STATE_CHANGED", "stage=INCOMING source=offer", id)
    }

    fun isTracking(id: String?): Boolean = id != null && eventId == id
    fun isIncoming(id: String): Boolean = eventId == id && stage == YandexStage.INCOMING
    fun stageFor(id: String): YandexStage? = if (eventId == id) stage else null
    fun isPending(): Boolean = pending != null
    fun stop(id: String?) {
        if (id != null && eventId == id) {
            pending = null
            eventId = null
        }
    }

    fun request(service: YandexAccessibilityService, id: String, root: AccessibilityNodeInfo?) {
        val context: Context = service
        val action = YandexActionPolicy.actionFor(stage)
        MonitorLog.write(context, "DEBUG", "ORDER_ACTION_REQUEST", "action=${action?.name ?: "none"}", id)
        val overlay = OverlayManager.get(context)
        fun fail(reason: String) {
            MonitorLog.write(context, "WARN", "ACTION_CLICK_FAILED", "reason=$reason", id)
            overlay.actionFailed(id)
        }
        if (!isTracking(id) || overlay.currentId != id) return fail("offer_not_active")
        if (pending != null) return fail("confirmation_pending")
        if (action == null) return fail("order_already_completed")
        if (root?.packageName?.toString() != YandexDiagnostics.YANDEX_PRO_PACKAGE)
            return fail("yandex_not_foreground")

        val nodes = mutableListOf<AccessibilityNodeInfo>()
        val texts = mutableListOf<String>()
        val targets = mutableListOf<AccessibilityNodeInfo>()
        val labels = mutableListOf<Rect>()
        val sliders = mutableListOf<Rect>()
        val windowBounds = Rect().also { root.getBoundsInScreen(it) }
        var truncated = false
        fun walk(node: AccessibilityNodeInfo, depth: Int) {
            if (depth > 40 || nodes.size >= 500) { truncated = true; return }
            if (!node.isVisibleToUser || node.isPassword || node.isEditable) return
            node.text?.toString()?.let(texts::add)
            node.contentDescription?.toString()?.takeIf { it != node.text?.toString() }?.let(texts::add)
            if (YandexActionPolicy.matches(action, node.text?.toString()) ||
                YandexActionPolicy.matches(action, node.contentDescription?.toString())) {
                val labelBounds = Rect()
                node.getBoundsInScreen(labelBounds)
                if (node.packageName?.toString() == YandexDiagnostics.YANDEX_PRO_PACKAGE &&
                    node.isEnabled && YandexActionPolicy.usableGestureLabel(
                        labelBounds.left, labelBounds.top, labelBounds.right, labelBounds.bottom,
                        windowBounds.left, windowBounds.top, windowBounds.right, windowBounds.bottom) &&
                    labels.none { it == labelBounds }) labels.add(labelBounds)
                var candidate: AccessibilityNodeInfo? = node
                var hops = 0
                var foundClickTarget = false
                while (candidate != null && hops <= 8) {
                    val bounds = Rect()
                    candidate.getBoundsInScreen(bounds)
                    if (action == YandexAction.START && candidate.packageName?.toString() == YandexDiagnostics.YANDEX_PRO_PACKAGE &&
                        candidate.isVisibleToUser && candidate.isEnabled &&
                        YandexActionPolicy.usableSliderBounds(bounds.left, bounds.top, bounds.right, bounds.bottom,
                            labelBounds.centerX(), labelBounds.centerY(), windowBounds.left, windowBounds.top,
                            windowBounds.right, windowBounds.bottom) && sliders.none { it == bounds }) sliders.add(bounds)
                    if (!foundClickTarget && YandexActionPolicy.usableTarget(candidate.packageName?.toString(),
                            candidate.isVisibleToUser, candidate.isEnabled, candidate.isClickable,
                            candidate.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK },
                            !bounds.isEmpty) && YandexActionPolicy.usableClickBounds(
                                bounds.left, bounds.top, bounds.right, bounds.bottom,
                                labelBounds.centerX(), labelBounds.centerY(), windowBounds.height())) {
                        if (targets.none { it == candidate }) targets.add(candidate)
                        foundClickTarget = true
                    }
                    candidate = candidate.parent?.also(nodes::add)
                    hops++
                }
            }
            if (node.childCount > 500) truncated = true
            for (index in 0 until node.childCount.coerceAtMost(500)) {
                val child = node.getChild(index) ?: continue
                nodes.add(child)
                walk(child, depth + 1)
            }
        }
        try {
            walk(root, 0)
            if (truncated) return fail("tree_truncated")
            val observed = YandexActionPolicy.screenStage(texts)
            if (observed != stage) return fail("screen_stage_mismatch")
            if (action == YandexAction.ACCEPT && !YandexCardParser.parse(texts).offerVisible)
                return fail("incoming_offer_not_visible")
            if (targets.size > 1) return fail("ambiguous_buttons")
            val slider = if (action == YandexAction.START && labels.size == 1)
                sliders.maxByOrNull { it.width() } else null
            if (targets.size == 1 && slider == null && !preferGesture) {
                MonitorLog.write(context, "DEBUG", "ACTION_NODE_FOUND", "action=${action.name} source=accessibility", id)
                val clicked = runCatching { targets.single().performAction(AccessibilityNodeInfo.ACTION_CLICK) }
                    .getOrDefault(false)
                if (clicked) {
                    pending = action
                    pendingSince = SystemClock.uptimeMillis()
                    MonitorLog.write(context, "INFO", "ACTION_CLICK_SUCCESS", "action=${action.name} source=accessibility awaiting_confirmation=true", id)
                    overlay.actionPending(id)
                    YandexAccessibilityService.requestCapture(700)
                    return
                }
                preferGesture = true
                MonitorLog.write(context, "DEBUG", "ACTION_CLICK_FAILED", "reason=action_click_returned_false fallback=visible_label_gesture", id)
            }
            // Some Yandex Pro controls are drawn on a Canvas. Android exposes
            // the exact text label, but no clickable node or ancestor.
            if (labels.size != 1) return fail(if (labels.isEmpty()) "button_not_found label_nodes=0" else "ambiguous_label_bounds")
            val bounds = labels.single()
            if (action == YandexAction.START && slider == null) return fail("slider_not_identified")
            val y = if (slider == null) bounds.centerY() else slider.centerY()
            val inset = slider?.let { maxOf(16, it.height() / 2) } ?: 0
            val x = if (slider == null) bounds.centerX() else slider.left + inset
            val endX = if (slider == null) x else slider.right - inset
            if ((slider == null && overlay.coversPoint(x, y)) ||
                (slider != null && overlay.coversHorizontalSegment(x, endX, y))) return fail("label_obscured_by_overlay")
            val source = if (slider == null) "visible_label_gesture" else "visible_slider_gesture"
            MonitorLog.write(context, "DEBUG", "ACTION_NODE_FOUND", "action=${action.name} source=$source", id)
            pending = action
            pendingSince = SystemClock.uptimeMillis()
            val dispatched = runCatching {
                val callback: (Boolean) -> Unit = callback@{ completed ->
                    if (!isTracking(id) || pending != action) return@callback
                    if (completed) {
                        MonitorLog.write(context, "INFO", "ACTION_CLICK_SUCCESS",
                            "action=${action.name} source=$source awaiting_confirmation=true", id)
                        YandexAccessibilityService.requestCapture(100)
                    } else {
                        pending = null
                        fail("gesture_cancelled")
                    }
                }
                if (slider == null) service.tapYandexLabel(x, y, callback)
                else service.swipeYandexSlider(x, endX, y, callback)
            }.getOrDefault(false)
            if (!dispatched) { pending = null; return fail("gesture_rejected_or_yandex_not_foreground") }
            overlay.actionPending(id)
            YandexAccessibilityService.requestCapture(700)
        } catch (e: Exception) {
            fail("${e.javaClass.simpleName}")
        } finally {
            for (node in nodes.asReversed()) recycle(node)
        }
    }

    fun onSnapshot(context: Context, texts: List<String>, isYandex: Boolean) {
        val id = eventId ?: return
        if (OverlayManager.get(context).currentId != id) return
        if (!isYandex) return
        val observed = YandexActionPolicy.screenStage(texts)
        if (YandexActionPolicy.confirmsNext(stage, observed)) {
            stage = observed!!
            pending = null
            preferGesture = false
            MonitorLog.write(context, "INFO", "YANDEX_STATE_CHANGED", "stage=${stage.name} source=screen", id)
            OverlayManager.get(context).actionConfirmed(id, stage)
            return
        }
        if (pending != null && SystemClock.uptimeMillis() - pendingSince > CONFIRM_TIMEOUT_MS) {
            pending = null
            preferGesture = true
            MonitorLog.write(context, "WARN", "ACTION_CLICK_FAILED", "reason=state_not_confirmed", id)
            OverlayManager.get(context).actionFailed(id)
        }
    }

    @Suppress("DEPRECATION")
    private fun recycle(node: AccessibilityNodeInfo) { runCatching { node.recycle() } }
}
