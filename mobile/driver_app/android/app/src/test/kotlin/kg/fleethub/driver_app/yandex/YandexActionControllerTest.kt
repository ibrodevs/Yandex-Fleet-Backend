package kg.fleethub.driver_app.yandex

import org.junit.Assert.*
import org.junit.Test

class YandexActionControllerTest {
    @Test fun everyActionRequiresTheNextYandexScreenState() {
        val transitions = listOf(
            Triple(YandexStage.INCOMING, YandexAction.ACCEPT, listOf("На месте")),
            Triple(YandexStage.ACCEPTED, YandexAction.ARRIVED, listOf("Поехали")),
            Triple(YandexStage.WAITING, YandexAction.START, listOf("Завершить")),
            Triple(YandexStage.RIDING, YandexAction.FINISH, listOf("Заказ завершён")),
        )
        for ((stage, action, nextScreen) in transitions) {
            assertEquals(action, YandexActionPolicy.actionFor(stage))
            assertTrue(YandexActionPolicy.confirmsNext(stage, YandexActionPolicy.screenStage(nextScreen)))
            assertFalse(YandexActionPolicy.confirmsNext(stage, YandexActionPolicy.screenStage(listOf(action.title))))
        }
        assertNull(YandexActionPolicy.actionFor(YandexStage.COMPLETED))
    }

    @Test fun ambiguousOrPartialLabelsCannotSelectAnAction() {
        assertNull(YandexActionPolicy.screenStage(listOf("На месте", "Поехали")))
        assertNull(YandexActionPolicy.screenStage(listOf("Принять условия", "Завершить смену")))
        assertFalse(YandexActionPolicy.matches(YandexAction.ACCEPT, "Принять условия"))
        assertFalse(YandexActionPolicy.matches(YandexAction.FINISH, "Завершить смену"))
        assertFalse(YandexActionPolicy.confirmsNext(YandexStage.INCOMING, YandexStage.RIDING))
        assertTrue(YandexActionPolicy.matches(YandexAction.ACCEPT, "+130 ₽\nПринять"))
        assertEquals(YandexStage.INCOMING, YandexActionPolicy.screenStage(listOf("+130 ₽\nПринять")))
    }

    @Test fun actionTargetMustBelongToYandexAndBeVisibleEnabledAndClickable() {
        assertTrue(YandexActionPolicy.usableTarget("ru.yandex.taximeter", true, true, true, true, true))
        assertFalse(YandexActionPolicy.usableTarget("kg.fleethub.driver_app", true, true, true, true, true))
        assertFalse(YandexActionPolicy.usableTarget("ru.yandex.taximeter", false, true, true, true, true))
        assertFalse(YandexActionPolicy.usableTarget("ru.yandex.taximeter", true, false, true, true, true))
        assertFalse(YandexActionPolicy.usableTarget("ru.yandex.taximeter", true, true, false, true, true))
        assertFalse(YandexActionPolicy.usableTarget("ru.yandex.taximeter", true, true, true, false, true))
        assertFalse(YandexActionPolicy.usableTarget("ru.yandex.taximeter", true, true, true, true, false))
    }

    @Test fun canvasGestureRequiresSmallVisibleLabelInsideYandexWindow() {
        assertTrue(YandexActionPolicy.usableGestureLabel(400, 1500, 500, 1540, 0, 24, 1080, 2200))
        assertFalse(YandexActionPolicy.usableGestureLabel(400, 1500, 500, 1540, 0, 24, 350, 2200))
        assertFalse(YandexActionPolicy.usableGestureLabel(0, 200, 1080, 1800, 0, 24, 1080, 2200))
        assertTrue(YandexActionPolicy.usableClickBounds(350, 1440, 800, 1580, 450, 1520, 2200))
        assertFalse(YandexActionPolicy.usableClickBounds(0, 24, 1080, 2200, 450, 1520, 2200))
    }

    @Test fun rideStartSwipeRequiresAVisibleBottomSliderAnchoredByTheExactLabel() {
        assertTrue(YandexActionPolicy.usableSliderBounds(
            80, 1900, 1000, 2050, 300, 1970, 0, 24, 1080, 2200))
        assertFalse(YandexActionPolicy.usableSliderBounds(
            80, 200, 1000, 350, 300, 270, 0, 24, 1080, 2200))
        assertFalse(YandexActionPolicy.usableSliderBounds(
            80, 1900, 1000, 2050, 1050, 1970, 0, 24, 1080, 2200))
        assertFalse(YandexActionPolicy.usableSliderBounds(
            80, 1600, 1000, 2100, 300, 1900, 0, 24, 1080, 2200))
    }
}
