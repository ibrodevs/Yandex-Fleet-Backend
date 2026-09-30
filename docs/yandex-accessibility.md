# Диагностика входящих предложений Yandex Pro

Реализован диагностический этап 1 из задания. Детектор, парсер, overlay входящих предложений и нажатия в Yandex ещё не реализованы: пункт 26 требует сначала проверить Accessibility tree реального входящего предложения. Подключённый при разработке эмулятор не содержит ru.yandex.taximeter. Макет дерева не является подтверждением реального интерфейса.

## Существующая интеграция

Flutter: mobile/driver_app. Application ID: kg.fleethub.driver_app. minSdk 26, targetSdk/compileSdk 36 (из установленного Flutter). Существующие fleet/overlay, FCM, OrderOverlayService specialUse, авторизация и API сохранены. Новых uses-permission нет. Добавлена видимость пакета Yandex и AccessibilityService с BIND_ACCESSIBILITY_SERVICE.

## Проверка

```sh
cd mobile/driver_app
flutter analyze
flutter test
flutter build apk --debug
adb devices -l
adb -s DEVICE_SERIAL shell pm path ru.yandex.taximeter
adb -s DEVICE_SERIAL install -r build/app/outputs/flutter-apk/app-debug.apk
```

В приложении: Настройки → Интеграция с Yandex Pro → Специальные возможности → Включить. Пользователь самостоятельно подтверждает доступ в Android. Экран объясняет назначение сервиса и запись данных. Для установки из стороннего источника Android может потребовать разрешить ограниченные настройки в информации о приложении.

1. Включить запись дерева в debug-сборке, затем открыть Yandex Pro.
2. Получить реальное входящее предложение, вернуться в диагностику и скопировать журнал до выключения записи.
3. Снять отдельно состояния карты, входящего предложения, принятого заказа, пропуска и истечения предложения. Указать версию Yandex Pro и Android. Не публиковать адреса и личные данные пассажиров.
4. Проверить время события, rootAvailable, nodes и truncated. Если truncated=true, требуется адаптировать бюджет обхода; неполный снимок не считать доказательством отсутствия элементов.
5. Выключить запись: журнал очищается. При отключении Accessibility или уничтожении процесса данные также очищаются. Повторно проверить подключение сервиса после перезапуска.

Настройка Gradle YANDEX_BRIDGE_DEBUG по умолчанию true; подробные снимки дополнительно ограничены BuildConfig.DEBUG и явным переключателем записи. Отключить сбор: ORG_GRADLE_PROJECT_YANDEX_BRIDGE_DEBUG=false flutter build apk --debug. Release никогда не собирает подробные снимки.

Журнал ограничен 30 снимками / 256000 символами и хранится только в памяти. Обход ограничен 500 узлами, глубиной 40 и бюджетом 40 мс, выполняется не чаще одного запланированного снимка за 300 мс. Пароли и редактируемые поля с их поддеревьями исключены; тексты с признаками секретов редактируются. Журнал всё равно следует проверять перед передачей: произвольный текст интерфейса невозможно гарантированно классифицировать. Нет файловых логов, Logcat-дампов и сетевой отправки.

Каналы fleet/yandex/methods и fleet/yandex/events независимы от существующего overlay. На этом этапе доступны getServiceStatus, isYandexInstalled, isAccessibilityEnabled, canDrawOverlays, openAccessibilitySettings, openOverlaySettings, setDebugRecording, getDebugLog, clearDebugLog; события diagnostic_event и service_status_changed. Методы принятия/пропуска намеренно не подключены.

Для native instrumentation tests:

```sh
cd mobile/driver_app/android
./gradlew app:connectedDebugAndroidTest -Pandroid.testInstrumentationRunnerArguments.class=kg.fleethub.driver_app.YandexDiagnosticsTest
```

После подтверждения реального дерева следующий этап — YandexOfferDetector и YandexOfferParser с тестовыми наборами из обезличенных снимков. Затем информационный overlay, lifecycle и подтверждённые пользователем действия — в порядке задания.

Конфигурация сервиса: https://developer.android.com/guide/topics/ui/accessibility/views/service

## Изменённые файлы

- `mobile/driver_app/android/app/build.gradle.kts` — BuildConfig и флаг диагностики.
- `mobile/driver_app/android/app/src/main/AndroidManifest.xml` — сервис и видимость Yandex.
- `mobile/driver_app/android/app/src/main/kotlin/kg/fleethub/driver_app/MainActivity.kt` — регистрация plugin.
- `mobile/driver_app/android/app/src/main/kotlin/kg/fleethub/driver_app/yandex/YandexAccessibilityService.kt` — ограниченный обход дерева.
- `mobile/driver_app/android/app/src/main/kotlin/kg/fleethub/driver_app/yandex/YandexDiagnostics.kt` — статус и журнал.
- `mobile/driver_app/android/app/src/main/kotlin/kg/fleethub/driver_app/yandex/YandexBridgePlugin.kt` — Flutter channels.
- `mobile/driver_app/android/app/src/main/res/xml/yandex_accessibility.xml` — конфигурация сервиса.
- `mobile/driver_app/android/app/src/main/res/values/yandex_strings.xml` — описание доступа.
- `mobile/driver_app/lib/app.dart` — вход из настроек.
- `mobile/driver_app/lib/yandex/yandex_diagnostics_screen.dart` — экран диагностики.
- `mobile/driver_app/test/yandex_diagnostics_test.dart` — Flutter-тесты.
- `mobile/driver_app/android/app/src/androidTest/kotlin/kg/fleethub/driver_app/YandexDiagnosticsTest.kt` — Android-тесты.
- `docs/yandex-accessibility.md` — инструкция и границы реализации.

## Результат локальной проверки

30 сентября 2026: flutter analyze — без замечаний; flutter test — 53 теста прошли; flutter build apk --debug — успешно. Два Android instrumentation-теста на Pixel_7 AVD / Android 15 прошли без пропусков и ошибок. Это проверяет регистрацию и конфигурацию сервиса, ограничение журнала и Flutter-экран, но не подтверждает получение реального дерева Yandex Pro или обнаружение заказа.
