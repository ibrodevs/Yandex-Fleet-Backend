package kg.fleethub.driver_app.overlay

import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import kg.fleethub.driver_app.yandex.YandexAccessibilityService
import kg.fleethub.driver_app.yandex.YandexActionController
import kg.fleethub.driver_app.yandex.YandexActionPolicy
import kg.fleethub.driver_app.yandex.YandexStage
import kg.fleethub.driver_app.yandex.MonitorLog

class OverlayManager private constructor(private val context: Context) {
    companion object {
        private var singleton: OverlayManager? = null
        fun get(context: Context): OverlayManager = singleton
            ?: OverlayManager(context.applicationContext).also { singleton = it }
    }

    private val windows = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private val handler = Handler(Looper.getMainLooper())
    private var view: View? = null
    private var body: LinearLayout? = null
    private var actionButton: Button? = null
    private var openButton: Button? = null
    private var actionMessage: TextView? = null
    private var headerText: TextView? = null
    private var currentOrder: JSONObject? = null
    private var actionStage = YandexStage.INCOMING
    var currentId: String? = null
        private set

    private fun dp(value: Int) = (value * context.resources.displayMetrics.density).toInt()

    fun hide() {
        handler.removeCallbacksAndMessages(null)
        YandexActionController.stop(currentId)
        view?.let { runCatching { windows.removeView(it) } }
        view = null
        body = null
        actionButton = null
        openButton = null
        actionMessage = null
        headerText = null
        currentOrder = null
        currentId = null
    }

    /** Refresh the content of the same window; never reopen a dismissed or different offer. */
    fun update(order: JSONObject): Boolean {
        val id = OrderDelivery.value(order, "order_id") ?: OrderDelivery.value(order, "event_id")
        val container = body ?: return false
        if (id == null || id != currentId || view == null) return false
        currentOrder = order
        render(container, order, OverlayPreferences(context).settings)
        scheduleAutoHide(order)
        return true
    }

    private fun render(container: LinearLayout, order: JSONObject, settings: JSONObject) {
        container.removeAllViews()
        val localOffer = order.optString("source") == "yandex_notification"
        fun label(text: String, size: Float = 16f, color: Int = Color.WHITE) {
            container.addView(TextView(context).apply {
                this.text = text
                textSize = size
                setTextColor(color)
                setPadding(0, dp(5), 0, dp(5))
                if (size >= 20) setTypeface(null, Typeface.BOLD)
            })
        }
        if (settings.optBoolean("show_tariff", true)) {
            OrderDelivery.value(order, "tariff_title")?.let { label("Тариф: $it", 20f) }
        }
        OrderDelivery.value(order, "order_type")?.let { label("Тип: $it", 14f, Color.LTGRAY) }
        if (settings.optBoolean("show_distance", true)) {
            if (localOffer) OrderDelivery.value(order, "pickup_eta_minutes")?.let {
                label("Подача: ~$it мин", 14f, Color.LTGRAY)
            }
            val duration = OrderDelivery.value(order, "duration_minutes")
            if (duration != null) label(if (localOffer) "Время поездки: ~$duration мин" else "Время: ~$duration мин", 14f, Color.LTGRAY)
            else if (localOffer) label("Время поездки: нет в предложении", 14f, Color.LTGRAY)
            OrderDelivery.value(order, "distance_km")?.let { label("Расстояние: $it км", 14f, Color.LTGRAY) }
            if (localOffer) OrderDelivery.value(order, "pickup_distance_km")?.let {
                label("До подачи: $it км", 14f, Color.LTGRAY)
            }
        }
        if (settings.optBoolean("show_price", true)) {
            OrderDelivery.value(order, "price")?.let { price ->
                val currency = when (OrderDelivery.value(order, "currency")) {
                    "RUB", "₽" -> "₽"
                    "KGS" -> "сом"
                    else -> OrderDelivery.value(order, "currency").orEmpty()
                }
                label("Цена: $price $currency".trim(), 23f)
            }
            if (localOffer && OrderDelivery.value(order, "price") == null)
                label("Цена: нет в предложении", 16f, Color.LTGRAY)
        }
        OrderDelivery.value(order, "payment_method")?.let { payment ->
            label("Оплата: ${when (payment) {
                "card" -> "карта"; "cashless" -> "безнал"; "cash" -> "наличные"
                "corp", "corporate" -> "корпоративный"; "prepaid" -> "предоплата"
                "internal" -> "внутренний"; "other" -> "другое"; else -> payment
            }}", 14f, Color.LTGRAY)
        }
        if (localOffer && OrderDelivery.value(order, "payment_method") == null)
            label("Оплата: нет в предложении", 14f, Color.LTGRAY)
        if (settings.optBoolean("show_address", true)) {
            val pickup = OrderDelivery.value(order, "pickup")
            if (pickup != null) label("Откуда: $pickup")
            else if (localOffer) label("Откуда: уточняется", 14f, Color.LTGRAY)
            val destination = OrderDelivery.value(order, "destination")
            if (destination != null) label("Куда: $destination")
            else if (localOffer) label("Куда: уточняется", 14f, Color.LTGRAY)
        }
        if (!localOffer && listOf("tariff_title", "order_type", "price", "pickup", "destination", "duration_minutes")
                .all { OrderDelivery.value(order, it) == null }) {
            label("Откройте Яндекс Про для деталей заказа", 16f, Color.LTGRAY)
        }
    }

    private fun scheduleAutoHide(order: JSONObject) {
        handler.removeCallbacksAndMessages(null)
        val settings = OverlayPreferences(context).settings
        if (order.optString("source") == "yandex_notification" && actionStage in
            setOf(YandexStage.ACCEPTED, YandexStage.WAITING, YandexStage.RIDING)) return
        if (!settings.optBoolean("auto_hide", true)) return
        val configured = settings.optInt("display_seconds", 15).coerceIn(5, 30)
        val incompleteLocal = order.optString("source") == "yandex_notification" &&
            listOf("price", "payment_method", "pickup", "destination")
                .any { OrderDelivery.value(order, it) == null }
        val seconds = if (incompleteLocal) maxOf(configured, 30) else configured
        handler.postDelayed({ hide() }, seconds * 1000L)
    }

    fun show(order: JSONObject) {
        hide()
        actionStage = YandexStage.INCOMING
        val prefs = OverlayPreferences(context)
        val settings = prefs.settings
        val root = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22), dp(18), dp(22), dp(16))
            background = GradientDrawable().apply {
                setColor(Color.rgb(25, 34, 29))
                cornerRadius = dp(24).toFloat()
                setStroke(dp(1), Color.rgb(66, 81, 68))
            }
            alpha = 1f - settings.optInt("transparency", 0).coerceIn(0, 80) / 100f
            elevation = dp(12).toFloat()
        }
        val header = TextView(context).apply {
            text = when {
                order.optBoolean("is_test") -> "ПРОВЕРКА ЭКРАНА · ПРИМЕР"
                order.optString("data_kind") == "confirmed_order" -> "●  ЗАКАЗ ЯНДЕКС · ПОДТВЕРЖДЁН"
                else -> "●  ВХОДЯЩЕЕ ПРЕДЛОЖЕНИЕ"
            }
            textSize = 12f
            setTextColor(Color.rgb(216, 243, 106))
            setPadding(0, 0, 0, dp(12))
        }
        root.addView(header)
        headerText = header
        val content = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        root.addView(content)
        render(content, order, settings)
        val localOffer = order.optString("source") == "yandex_notification" && !order.optBoolean("is_test")
        if (localOffer) {
            actionMessage = TextView(context).apply {
                textSize = 14f
                setTextColor(Color.WHITE)
                visibility = View.GONE
            }.also { root.addView(it) }
            actionButton = Button(context).apply {
                text = YandexActionPolicy.actionFor(YandexStage.INCOMING)!!.title
                setOnClickListener {
                    currentId?.let { id -> YandexAccessibilityService.requestAction(context, id) }
                }
            }.also { root.addView(it, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(50))) }
            openButton = Button(context).apply {
                text = "Открыть Yandex Pro"
                visibility = View.GONE
                setOnClickListener {
                    try { context.startActivity(OrderDelivery.openIntent(context, currentOrder ?: order)) }
                    catch (e: Exception) {
                        MonitorLog.write(context, "ERROR", "ACTION_CLICK_FAILED", "reason=open_yandex_failed error=${e.javaClass.simpleName}", currentId)
                    }
                }
            }.also { root.addView(it, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(50))) }
        }
        root.addView(Button(context).apply { text = "Закрыть"; setOnClickListener { hide() } },
            LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(50)))
        val width = minOf(dp(350), context.resources.displayMetrics.widthPixels - dp(24))
        val params = WindowManager.LayoutParams(width, WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            PixelFormat.TRANSLUCENT).apply {
            gravity = Gravity.TOP or Gravity.START
            x = prefs.store.getInt("x", dp(12))
            y = prefs.store.getInt("y", dp(100))
        }
        var startX = 0f
        var startY = 0f
        var originalX = 0
        var originalY = 0
        header.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    startX = event.rawX; startY = event.rawY
                    originalX = params.x; originalY = params.y
                }
                MotionEvent.ACTION_MOVE -> {
                    params.x = (originalX + event.rawX - startX).toInt()
                        .coerceIn(0, maxOf(0, context.resources.displayMetrics.widthPixels - width))
                    params.y = (originalY + event.rawY - startY).toInt()
                        .coerceIn(0, maxOf(0, context.resources.displayMetrics.heightPixels - root.height))
                    windows.updateViewLayout(root, params)
                }
                MotionEvent.ACTION_UP -> prefs.store.edit().putInt("x", params.x).putInt("y", params.y).apply()
            }
            true
        }
        windows.addView(root, params)
        view = root
        body = content
        currentOrder = order
        currentId = OrderDelivery.value(order, "order_id") ?: OrderDelivery.value(order, "event_id")
        scheduleAutoHide(order)
    }

    fun actionPending(id: String) {
        if (currentId != id) return
        handler.removeCallbacksAndMessages(null)
        actionButton?.apply { text = "Подтверждаем..."; isEnabled = false }
        actionMessage?.visibility = View.GONE
    }

    fun actionFailed(id: String) {
        if (currentId != id) return
        actionButton?.visibility = View.GONE
        actionMessage?.apply { text = "Не удалось выполнить действие"; visibility = View.VISIBLE }
        openButton?.visibility = View.VISIBLE
    }

    fun actionConfirmed(id: String, stage: YandexStage) {
        if (currentId != id) return
        actionStage = stage
        headerText?.text = if (stage == YandexStage.COMPLETED) "●  ЗАКАЗ ЗАВЕРШЁН" else "●  ЗАКАЗ В РАБОТЕ"
        actionMessage?.visibility = View.GONE
        openButton?.visibility = View.GONE
        val next = YandexActionPolicy.actionFor(stage)
        actionButton?.apply {
            visibility = if (next == null) View.GONE else View.VISIBLE
            isEnabled = next != null
            text = next?.title.orEmpty()
        }
        currentOrder?.let(::scheduleAutoHide)
    }
}
