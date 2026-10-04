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
}
