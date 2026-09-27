package kg.fleethub.driver_app.overlay
import android.content.Context
import org.json.JSONObject
class OverlayPreferences(context: Context) {
    val store = context.getSharedPreferences("fleet_overlay", Context.MODE_PRIVATE)
    var settings: JSONObject
        get() = JSONObject(store.getString("settings", "{}") ?: "{}")
        set(value) { store.edit().putString("settings", value.toString()).apply() }
    var driverMode: Boolean
        get() = store.getBoolean("driver_mode",false)
        set(value) { store.edit().putBoolean("driver_mode",value).apply() }
    var active: Boolean
        get() = store.getBoolean("active",false)
        set(value) { store.edit().putBoolean("active",value).apply() }
    fun clear() { store.edit().clear().apply() }
}
