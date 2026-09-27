package kg.fleethub.driver_app.overlay
import android.content.Context
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Handler
import android.os.Looper
import android.view.*
import android.widget.*
import org.json.JSONObject

class OverlayManager private constructor(private val context: Context) {
    companion object {
        private var singleton: OverlayManager? = null
        fun get(context: Context): OverlayManager = singleton ?: OverlayManager(context.applicationContext).also { singleton=it }
    }
    private val windows=context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private val handler=Handler(Looper.getMainLooper())
    private var view: View?=null
    var currentId: String?=null
        private set
    private fun dp(value: Int)=(value*context.resources.displayMetrics.density).toInt()
    fun hide() { handler.removeCallbacksAndMessages(null); view?.let { try { windows.removeView(it) } catch (_: Exception) {} }; view=null; currentId=null }
    fun show(order: JSONObject) {
        hide()
        val prefs=OverlayPreferences(context)
        val s=prefs.settings
        val root=LinearLayout(context).apply {
            orientation=LinearLayout.VERTICAL; setPadding(dp(22),dp(18),dp(22),dp(16))
            background=GradientDrawable().apply { setColor(Color.rgb(25,34,29)); cornerRadius=dp(24).toFloat(); setStroke(dp(1),Color.rgb(66,81,68)) }
            alpha=1f-s.optInt("transparency",0).coerceIn(0,80)/100f
            elevation=dp(12).toFloat()
        }
        fun label(text: String,size: Float=16f,color: Int=Color.WHITE) {
            root.addView(TextView(context).apply { this.text=text; textSize=size; setTextColor(color); setPadding(0,dp(5),0,dp(5)); if(size>=20) setTypeface(null,Typeface.BOLD) })
        }
        val header=TextView(context).apply { text=if(order.optBoolean("is_test")) "ПРОВЕРКА ЭКРАНА · ПРИМЕР" else "●  ВХОДЯЩИЙ ЗАКАЗ"; textSize=12f;setTextColor(Color.rgb(216,243,106));setPadding(0,0,0,dp(12)) }
        root.addView(header)
        if(s.optBoolean("show_tariff",true)) label(OrderDelivery.text(order,"tariff_title"),23f)
        if(s.optBoolean("show_distance",true)) label("${OrderDelivery.text(order,"distance_km")} км · ${OrderDelivery.text(order,"duration_minutes")} мин",14f,Color.LTGRAY)
        if(s.optBoolean("show_price",true)) label("${OrderDelivery.text(order,"price")} ${if(order.optString("currency")=="RUB") "₽" else OrderDelivery.text(order,"currency")}",26f)
        label(when(order.optString("payment_method")){"card"->"Безнал";"cash"->"Наличные";else->OrderDelivery.text(order,"payment_method")},14f,Color.LTGRAY)
        if(s.optBoolean("show_address",true)) { label("А  ${OrderDelivery.text(order,"pickup")}"); label("Б  ${OrderDelivery.text(order,"destination")}") }
        val buttons=LinearLayout(context)
        buttons.addView(Button(context).apply { text="Открыть";setOnClickListener { context.startActivity(OrderDelivery.openIntent(context,order));hide() } },LinearLayout.LayoutParams(0,dp(50),1f))
        buttons.addView(Button(context).apply { text="Закрыть";setOnClickListener {hide()} },LinearLayout.LayoutParams(0,dp(50),1f))
        root.addView(buttons)
        val width=minOf(dp(350),context.resources.displayMetrics.widthPixels-dp(24))
        val params=WindowManager.LayoutParams(width,WindowManager.LayoutParams.WRAP_CONTENT,WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,PixelFormat.TRANSLUCENT).apply { gravity=Gravity.TOP or Gravity.START;x=prefs.store.getInt("x",dp(12));y=prefs.store.getInt("y",dp(100)) }
        var startX=0f;var startY=0f;var originalX=0;var originalY=0
        header.setOnTouchListener { _,event ->
            when(event.action){MotionEvent.ACTION_DOWN->{startX=event.rawX;startY=event.rawY;originalX=params.x;originalY=params.y};MotionEvent.ACTION_MOVE->{params.x=(originalX+event.rawX-startX).toInt().coerceIn(0,maxOf(0,context.resources.displayMetrics.widthPixels-width));params.y=(originalY+event.rawY-startY).toInt().coerceIn(0,maxOf(0,context.resources.displayMetrics.heightPixels-root.height));windows.updateViewLayout(root,params)};MotionEvent.ACTION_UP->{prefs.store.edit().putInt("x",params.x).putInt("y",params.y).apply()}};true
        }
        windows.addView(root,params);view=root;currentId=order.optString("order_id")
        if(s.optBoolean("auto_hide",true)) handler.postDelayed({hide()},s.optInt("display_seconds",15).coerceIn(5,30)*1000L)
    }
}
