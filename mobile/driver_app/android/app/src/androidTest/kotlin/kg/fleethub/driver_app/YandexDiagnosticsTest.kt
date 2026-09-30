package kg.fleethub.driver_app

import android.accessibilityservice.AccessibilityServiceInfo
import android.content.ComponentName
import android.content.pm.PackageManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kg.fleethub.driver_app.yandex.YandexAccessibilityService
import kg.fleethub.driver_app.yandex.YandexDiagnostics
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class YandexDiagnosticsTest {
    @Test fun registeredServiceIsRestrictedToYandexAndCanReadTrees() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val intent = android.content.Intent("android.accessibilityservice.AccessibilityService")
            .setComponent(ComponentName(context, YandexAccessibilityService::class.java))
        val resolved = context.packageManager.resolveService(intent, PackageManager.GET_META_DATA)!!
        assertEquals("android.permission.BIND_ACCESSIBILITY_SERVICE", resolved.serviceInfo.permission)
        val manager = context.getSystemService(android.view.accessibility.AccessibilityManager::class.java)
        val info = manager.installedAccessibilityServiceList.single {
            it.resolveInfo.serviceInfo.packageName == context.packageName &&
                it.resolveInfo.serviceInfo.name == YandexAccessibilityService::class.java.name
        }
        assertArrayEquals(arrayOf("ru.yandex.taximeter"), info.packageNames)
        assertTrue(info.capabilities and AccessibilityServiceInfo.CAPABILITY_CAN_RETRIEVE_WINDOW_CONTENT != 0)
        assertFalse(info.isAccessibilityTool)
    }

    @Test fun journalIsBoundedAndClearedWhenRecordingStops() {
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            YandexDiagnostics.setRecording(true)
            repeat(100) { YandexDiagnostics.record(mapOf("time" to it), "x".repeat(10000)) }
            assertTrue(YandexDiagnostics.log().length < 260000)
            YandexDiagnostics.setRecording(false)
            assertEquals("", YandexDiagnostics.log())
            assertNull(YandexDiagnostics.lastEvent)
        }
    }
}
