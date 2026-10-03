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
    private var currentOrder: JSONObject? = null
    var currentId: String? = null
        private set

    private fun dp(value: Int) = (value * context.resources.displayMetrics.density).toInt()

    fun hide() {
        handler.removeCallbacksAndMessages(null)
        view?.let { runCatching { windows.removeView(it) } }
        view = null
        body = null
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
            OrderDelivery.value(order, "duration_minutes")?.let { label("Время: ~$it мин", 14f, Color.LTGRAY) }
            OrderDelivery.value(order, "distance_km")?.let { label("Расстояние: $it км", 14f, Color.LTGRAY) }
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
        }
        OrderDelivery.value(order, "payment_method")?.let { payment ->
            label("Оплата: ${when (payment) { "card" -> "безнал"; "cash" -> "наличные"; else -> payment }}", 14f, Color.LTGRAY)
        }
        if (settings.optBoolean("show_address", true)) {
            OrderDelivery.value(order, "pickup")?.let { label("Откуда: $it") }
            OrderDelivery.value(order, "destination")?.let { label("Куда: $it") }
        }
        if (listOf("tariff_title", "order_type", "price", "pickup", "destination", "duration_minutes")
                .all { OrderDelivery.value(order, it) == null }) {
            label("Откройте Яндекс Про для деталей заказа", 16f, Color.LTGRAY)
        }
    }

    private fun scheduleAutoHide(order: JSONObject) {
        handler.removeCallbacksAndMessages(null)
        val settings = OverlayPreferences(context).settings
        if (!settings.optBoolean("auto_hide", true)) return
        val configured = settings.optInt("display_seconds", 15).coerceIn(5, 30)
        val titleOnlyLocal = order.optString("source") == "yandex_notification" &&
            listOf("tariff_title", "price", "pickup", "destination").all { OrderDelivery.value(order, it) == null }
        val seconds = if (titleOnlyLocal) maxOf(configured, 30) else configured
        handler.postDelayed({ hide() }, seconds * 1000L)
    }

    fun show(order: JSONObject) {
        hide()
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
            text = if (order.optBoolean("is_test")) "ПРОВЕРКА ЭКРАНА · ПРИМЕР" else "●  ВХОДЯЩИЙ ЗАКАЗ"
            textSize = 12f
            setTextColor(Color.rgb(216, 243, 106))
            setPadding(0, 0, 0, dp(12))
        }
        root.addView(header)
        val content = LinearLayout(context).apply { orientation = LinearLayout.VERTICAL }
        root.addView(content)
        render(content, order, settings)
        val buttons = LinearLayout(context)
        buttons.addView(Button(context).apply {
            text = "Открыть"
            setOnClickListener {
                context.startActivity(OrderDelivery.openIntent(context, currentOrder ?: order))
                hide()
            }
        }, LinearLayout.LayoutParams(0, dp(50), 1f))
        buttons.addView(Button(context).apply { text = "Закрыть"; setOnClickListener { hide() } },
            LinearLayout.LayoutParams(0, dp(50), 1f))
        root.addView(buttons)
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
}
