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
        text != null && labels.getValue(action).matches(text.trim())

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
}

/** Only the accessibility service supplies a live Yandex Pro root to this controller. */
object YandexActionController {
    private const val CONFIRM_TIMEOUT_MS = 10_000L
    private var eventId: String? = null
    private var stage = YandexStage.INCOMING
    private var pending: YandexAction? = null
    private var pendingSince = 0L

    fun start(context: Context, id: String) {
        if (eventId == id) return
        eventId = id
        stage = YandexStage.INCOMING
        pending = null
        MonitorLog.write(context, "DEBUG", "YANDEX_STATE_CHANGED", "stage=INCOMING source=offer", id)
    }

    fun isTracking(id: String?): Boolean = id != null && eventId == id
    fun isIncoming(id: String): Boolean = eventId == id && stage == YandexStage.INCOMING
    fun isPending(): Boolean = pending != null
    fun stop(id: String?) {
        if (id != null && eventId == id) {
            pending = null
            eventId = null
        }
    }

    fun request(context: Context, id: String, root: AccessibilityNodeInfo?) {
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
        var truncated = false
        fun walk(node: AccessibilityNodeInfo, depth: Int) {
            if (depth > 40 || nodes.size >= 500) { truncated = true; return }
            if (!node.isVisibleToUser || node.isPassword || node.isEditable) return
            node.text?.toString()?.let(texts::add)
            node.contentDescription?.toString()?.takeIf { it != node.text?.toString() }?.let(texts::add)
            if (YandexActionPolicy.matches(action, node.text?.toString()) ||
                YandexActionPolicy.matches(action, node.contentDescription?.toString())) {
                var candidate: AccessibilityNodeInfo? = node
                var hops = 0
                while (candidate != null && hops <= 3) {
                    val bounds = Rect()
                    candidate.getBoundsInScreen(bounds)
                    if (YandexActionPolicy.usableTarget(candidate.packageName?.toString(),
                            candidate.isVisibleToUser, candidate.isEnabled, candidate.isClickable,
                            candidate.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK },
                            !bounds.isEmpty)) {
                        if (targets.none { it == candidate }) targets.add(candidate)
                        break
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
            if (targets.size != 1) return fail(if (targets.isEmpty()) "button_not_found" else "ambiguous_buttons")
            MonitorLog.write(context, "DEBUG", "ACTION_NODE_FOUND", "action=${action.name}", id)
            val clicked = runCatching { targets.single().performAction(AccessibilityNodeInfo.ACTION_CLICK) }
                .getOrDefault(false)
            if (!clicked) return fail("action_click_returned_false")
            pending = action
            pendingSince = SystemClock.uptimeMillis()
            MonitorLog.write(context, "INFO", "ACTION_CLICK_SUCCESS", "action=${action.name} awaiting_confirmation=true", id)
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
        if (pending != null && SystemClock.uptimeMillis() - pendingSince > CONFIRM_TIMEOUT_MS) {
            pending = null
            MonitorLog.write(context, "WARN", "ACTION_CLICK_FAILED", "reason=state_not_confirmed", id)
            OverlayManager.get(context).actionFailed(id)
            return
        }
        if (!isYandex || pending == null) return
        val observed = YandexActionPolicy.screenStage(texts)
        if (YandexActionPolicy.confirmsNext(stage, observed)) {
            stage = observed!!
            pending = null
            MonitorLog.write(context, "INFO", "YANDEX_STATE_CHANGED", "stage=${stage.name} source=screen", id)
            OverlayManager.get(context).actionConfirmed(id, stage)
        }
    }

    @Suppress("DEPRECATION")
    private fun recycle(node: AccessibilityNodeInfo) { runCatching { node.recycle() } }
}
