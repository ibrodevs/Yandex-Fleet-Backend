package kg.fleethub.driver_app

import android.app.NotificationManager
import android.content.Intent
import android.provider.Settings
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kg.fleethub.driver_app.overlay.*
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Local delivery tests, not a substitute for end-to-end Firebase tests. */
@RunWith(AndroidJUnit4::class)
class OverlayAcceptanceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private val context = instrumentation.targetContext
    private fun onMain(block: () -> Unit) = instrumentation.runOnMainSync(block)
    private fun order(id: String) = JSONObject().put("order_id",id).put("type","new_order").put("driver_id","test-driver").put("is_test",true).put("tariff_title","ПРОВЕРКА ЭКРАНА · пример").put("price",380).put("currency","RUB")
    private fun prepare() {
        OverlayPreferences(context).apply { active=true; store.edit().putString("driver_id","test-driver").apply(); settings=JSONObject().put("auto_hide",false) }
    }
    @After fun cleanup() {
        onMain { OverlayManager.get(context).hide(); context.stopService(Intent(context,OrderOverlayService::class.java)); OverlayPreferences(context).clear() }
        context.getSystemService(NotificationManager::class.java).cancelAll()
    }
    @Test fun testLocalOverlayAndClose() {
        assertTrue("Grant SYSTEM_ALERT_WINDOW app-op before running",Settings.canDrawOverlays(context))
        prepare()
        onMain {
            OverlayManager.get(context).show(order("local-test"))
            assertEquals("local-test",OverlayManager.get(context).currentId)
        }
        instrumentation.waitForIdleSync()
        Thread.sleep(250)
        val screenshot = instrumentation.uiAutomation.takeScreenshot()
        java.io.FileOutputStream(java.io.File(context.getExternalFilesDir(null), "overlay-test.png")).use {
            screenshot.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it)
        }
        onMain {
            OverlayManager.get(context).hide()
            assertNull(OverlayManager.get(context).currentId)
        }
    }
    @Test fun testBackgroundServiceDeliveryAndDeduplication() {
        prepare()
        val launch=context.packageManager.getLaunchIntentForPackage(context.packageName)!!.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        instrumentation.startActivitySync(launch)
        onMain { OverlayPreferences(context).driverMode=true;context.startForegroundService(Intent(context,OrderOverlayService::class.java)) }
        val deadline=System.currentTimeMillis()+5000
        while(OrderOverlayService.instance==null && System.currentTimeMillis()<deadline) Thread.sleep(50)
        assertNotNull(OrderOverlayService.instance)
        context.startActivity(Intent(Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        instrumentation.waitForIdleSync()
        onMain {
            OrderDelivery.deliver(context,order("background-test"))
            assertEquals("background-test",OverlayManager.get(context).currentId)
            OverlayManager.get(context).hide()
            OrderDelivery.deliver(context,order("background-test"))
            assertNull("Dismissed event must not reopen",OverlayManager.get(context).currentId)
        }
    }
    @Test fun testTitleOnlyYandexOfferShowsOverlay() {
        assertTrue("Grant SYSTEM_ALERT_WINDOW app-op before running", Settings.canDrawOverlays(context))
        prepare()
        onMain {
            OverlayPreferences(context).driverMode = true
            val eventId = "yandex_evt_title_only_${System.nanoTime()}"
            val offer = JSONObject().put("type", "new_order").put("source", "yandex_notification")
                .put("event_id", eventId).put("order_id", "")
                .put("driver_id", "test-driver")
            OrderDelivery.deliver(context, offer)
            assertEquals(eventId, OverlayManager.get(context).currentId)
            val enriched = JSONObject(offer.toString()).put("tariff_title", "Комфорт+")
                .put("price", "1564").put("currency", "RUB")
                .put("payment_method", "card").put("duration_minutes", "40")
                .put("pickup", "ул. Манаса, 45").put("destination", "проспект Чуй, 120")
            assertTrue(OverlayManager.get(context).update(enriched))
            assertEquals("The same offer must keep one overlay", eventId, OverlayManager.get(context).currentId)
            OverlayManager.get(context).hide()
            assertFalse("Dismissed offer must stay dismissed", OverlayManager.get(context).update(enriched))
        }
    }
    @Test fun testOffDutyNotificationFallback() {
        prepare()
        onMain {
            OrderDelivery.deliver(context,order("fallback-test"))
            assertNull(OverlayManager.get(context).currentId)
        }
        val active=context.getSystemService(NotificationManager::class.java).activeNotifications
        assertTrue(active.any { it.id=="fallback-test".hashCode() })
    }
}
