# Fleet Hub — установка и проверка

Исходники: `mobile/driver_app`. Основная платформа: Android 8+. Flutter 3.47.2 / Dart 3.13.2. Backend использует существующий FleetProvider; Telegram и Mini App остаются самостоятельными клиентами. Мобильный API отказывается работать в mock-режиме и с секретом JWT по умолчанию.

## Firebase

1. Создайте Firebase project и Android app с package `kg.fleethub.driver_app`.
2. Добавьте SHA-1 и SHA-256 сертификатов debug и release (`cd android && ./gradlew signingReport`). Для Google Play добавьте сертификат Play App Signing.
3. Скачайте `google-services.json` в `mobile/driver_app/android/app/`. Файл игнорируется Git. Пока его нет, приложение собирается и показывает экран подключения Firebase; SMS и push недоступны. Поддельного JSON в проекте нет.
4. Authentication → Sign-in method → Phone: включите провайдера, разрешённые регионы SMS и настройте биллинг/квоты проекта. Для разработки используйте Firebase test phone numbers. Не помещайте тестовые OTP в исходники.
5. Включите Firebase Cloud Messaging API v1. Создайте Firebase Admin service account; файл храните **только на backend**, вне репозитория и каталога static. Ограничьте права чтения файлом владельца процесса (`chmod 600`).
6. Для iOS зарегистрируйте bundle ID, добавьте `GoogleService-Info.plist` в Runner через Xcode с target membership. Включите Push Notifications capability и Background Modes → Remote notifications; загрузите APNs key в Firebase. Для Phone Auth настройте URL scheme из Firebase и APNs согласно документации. iOS не поддерживает overlay.

Официальные инструкции: [Phone Auth](https://firebase.google.com/docs/auth/flutter/phone-auth), [FCM](https://firebase.google.com/docs/cloud-messaging/flutter/get-started), [Android FGS specialUse](https://developer.android.com/develop/background-work/services/fgs/service-types#special-use).

## Backend

```bash
uv venv --python python3.12
uv pip install -r requirements.txt
```

Добавьте в серверный `.env` (существующие Yandex/Telegram параметры сохраняются):

```dotenv
APP_ENV=production
YANDEX_MOCK_MODE=false
MOBILE_ENABLED=true
MOBILE_DB_PATH=/absolute/private/path/mobile.sqlite3
MOBILE_JWT_EXPIRE_DAYS=30
MOBILE_ORDER_WATCHER_ENABLED=true
MOBILE_ORDER_POLL_INTERVAL_SECONDS=10
FIREBASE_PROJECT_ID=your-project
FIREBASE_CREDENTIALS_FILE=/absolute/private/path/firebase-admin.json
```

`SECRET_KEY` должен быть случайным, минимум 32 символа: `python -c 'import secrets; print(secrets.token_urlsafe(48))'`. Не меняйте существующий production SECRET_KEY без плана завершения старых сессий. Все web/worker процессы должны использовать одинаковые параметры и путь к mobile.sqlite3. SQLite автоматически создаёт мобильные таблицы при первом мобильном запросе, без изменения основной схемы backend. Файл содержит персональные данные и FCM tokens; храните его в приватном каталоге с резервным копированием. Подходит для одного узла PythonAnywhere, не для нескольких независимых серверов.

Перезапустите web app после установки зависимостей. Web startup не обращается к Firebase и не запускает watcher. Отсутствие Firebase не ломает Telegram и `/health/ready`. Мобильный login возвращает 503 до настройки Firebase.

### Отдельный worker на PythonAnywhere

Создайте одну Always-on task (нужен подходящий тариф):

```bash
cd /path/to/Yandex-Fleet-Backend && /path/to/.venv/bin/python -m app.mobile.worker
```

Не добавляйте цикл в ASGI startup. Единственный `python -m app.mobile.worker` запрашивает список заказов парка один раз за цикл через существующий provider и обслуживает **FCM и Telegram**. Yandex-интеграция, Telegram webhook и их настройки не меняются. Существующая пагинация, лимиты и lookback provider сохраняются. Активные заказы (`assigned`, `waiting`, `in_progress`) первого запуска считаются обнаруженными; завершённые и отменённые не создают события.

Общее событие `NEW_ORDER` имеет уникальность driver/order/type. Неудачные доставки повторяются независимо при следующих циклах, максимум **30 минут с первого обнаружения**, только пока тот же driver/order присутствует в актуальном списке активных заказов. После ошибки опроса отправка откладывается до следующего успешного опроса. Повтор использует последние поля и статус заказа; время обнаружения не сбрасывается. Каждая попытка ограничена 30 секундами. Telegram `retry_after` сохраняется в БД и соблюдается после перезапуска; пауза Telegram не задерживает FCM.

Хранение (таблицы автоматически добавляются в существующую mobile.sqlite3 без удаления старых данных):

- `mobile_deliveries`: прежняя FCM-dedup по event/device; успешные устройства не получают повтор при ошибке другого устройства.
- `mobile_telegram_deliveries`: один подтверждённый успех на event, с Telegram user ID, message ID и временем. Перепривязка после успешной отправки не уведомляет о том же событии заново.
- `mobile_delivery_attempts`: число попыток, время последней попытки, следующий допустимый retry и тип ошибки отдельно для event/channel/recipient.

Перед каждой Telegram-попыткой `DriverLinkStore.get_by_driver_id()` читает текущую привязку из `TELEGRAM_BOT_DB_PATH`. Отсутствие привязки не блокирует мобильную доставку; если привязка появится в пределах окна, событие может доставиться в Telegram. Для Telegram не нужны mobile session или FCM device. Используются существующие `TELEGRAM_BOT_TOKEN`, `TELEGRAM_HTTP_PROXY` и HTML-presenter бота. Worker только отправляет сообщения: `getUpdates`, настройка webhook и второй polling-процесс не запускаются.

`MOBILE_ORDER_WATCHER_ENABLED=false` выключает весь watcher. `MOBILE_ENABLED=false` выключает только FCM-ветку и мобильный API, Telegram watcher продолжает работать. Мобильная настройка `notifications=false` также относится только к FCM. Отсутствующий bot token отключает Telegram-ветку, ошибка/отсутствие Firebase не препятствует Telegram. Lock-файл запрещает второй worker на том же узле. Для web и worker требуются одинаковые абсолютные пути к mobile.sqlite3 и Telegram-БД.

Structured JSON logs включают `order_watcher_started`, `order_watcher_poll_started/completed/failed`, `new_order_detected`, `order_delivery_attempt/sent/failed/skipped/deduplicated`, `order_delivery_channel_failed/disabled`. Поля: tick/event/order/driver ID, channel, recipient ID, attempt, duration_ms, reason, error_type и next_attempt_at. Токены, номера телефонов, адреса, содержимое сообщения и текст SDK-исключения не логируются. Успех одного канала не считается успехом другого.

FCM и Telegram не предоставляют здесь транзакцию совместно с SQLite: при падении между принятием сообщения провайдером и записью успеха, либо неопределённом результате timeout, возможен повтор. Durable dedup подавляет подтверждённые успешные доставки; абсолютная exactly-once доставка не обещается. Android дополнительно подавляет повтор одного order_id локально (последние 300 событий). Удалённые/просроченные мобильные сессии и отключённые устройства исключены из FCM. Worker не получает оффер раньше официального Fleet API.

## Сборка Android

```bash
cd mobile/driver_app
flutter pub get
flutter analyze
flutter test
flutter build apk --release
flutter build appbundle --release
```

По умолчанию URL — `https://yandexfeetbackend21.pythonanywhere.com/api/v1/mobile`. Другой HTTPS backend:

```bash
flutter build apk --release --dart-define=API_BASE_URL=https://example.com/api/v1/mobile
```

Артефакты: `build/app/outputs/flutter-apk/app-release.apk`, `build/app/outputs/bundle/release/app-release.aab`.

Без `android/key.properties` сборка использует debug-сертификат и пригодна только для внутренней проверки. Для публикации создайте собственный upload key, сохраните его вне Git, заполните `android/key.properties`:

```properties
storeFile=/absolute/path/upload.jks
storePassword=YOUR_PASSWORD
keyAlias=upload
keyPassword=YOUR_PASSWORD
```

Google Play потребует декларацию `specialUse` foreground service и обоснование SYSTEM_ALERT_WINDOW; одобрение магазина не подразумевается наличием сборки.

## Проверка на Android

1. Войти номером реального водителя. Убедиться, что профиль, автомобиль, баланс и заказы принадлежат ему.
2. Проверить GET чужого order ID: 404; отсутствие Bearer JWT и отозванная сессия: 401. Кнопок принятия/завершения нет.
3. Настройки → разрешить показ поверх приложений → вернуться → Проверить виджет. Тест явно отмечен как пример, не попадает на backend или в историю.
4. Перетащить карточку за заголовок; закрыть; повторить тест и проверить позицию, прозрачность, таймер.
5. Включить режим водителя при открытом приложении. Должно появиться постоянное уведомление с действием «Закончить смену».
6. Свернуть Flutter, открыть другое приложение, затем Яндекс Про. Отправить test push на своё зарегистрированное устройство:

```http
POST /api/v1/mobile/debug/test-notification
Authorization: Bearer <ваша-сессия>
Content-Type: application/json

{"device_id":"ваш-installation-id"}
```

Endpoint доступен только вне production и только для устройства текущего водителя. Сгенерированный order_id тестовый, «Открыть» ведёт на главную. Проверять через защищённый dev backend, не отключать production-проверку ради теста.

7. Отключить overlay permission и повторить: приходит обычное уведомление. При выключенном режиме водителя overlay также не показывается. При запрещённых системных уведомлениях ОС не позволяет показать уведомление: включите их в настройках Android.
8. Одно и то же реальное событие не должно повторяться. Изменение настроек, перезапуск worker, выход из аккаунта и смена пользователя не должны приводить к показу чужого заказа.
9. Проверить авиарежим: последние данные доступны, виден индикатор; после восстановления сети автоматически обновляются. HTTP 401/403 не заменяются кэшем.
10. Проверить выключение режима из постоянного уведомления, отзыв разрешения overlay, перезапуск процесса и блокировку экрана.

Нативный FirebaseMessagingService получает data push без Flutter Activity. Foreground service запускается пользователем из видимого Activity. Если ОС завершила сервис, приложение использует уведомление; автоматического перезапуска смены из фона нет. Android force-stop, отключение уведомлений, отсутствие Google Play Services и ограничения производителя могут остановить доставку. Экран блокировки не обходится.

## Что проверяется автоматически

`pytest -q`: существующие тесты и mobile auth, принадлежность заказов, отзыв сессии, обновление FCM token, settings validation, защита debug endpoint, повторы и retry worker.

`flutter test`: auth storage, order/null parser, notification envelope, offline repository, настройки, экран входа и отсутствие unsupported actions.

Полный SMS → реальный Yandex driver → FCM → overlay поверх Яндекс Про требует Firebase владельца, развёрнутого mobile API и физического Android/эмулятора с Google Play. Автотесты не заменяют эту проверку. iOS signing/APNs проверяются отдельно.

### Нативные тесты без Firebase

В `android/app/src/androidTest` есть instrumentation-тесты прямой локальной доставки: overlay, закрытие, подавление повторов после закрытия, показ поверх Android Settings при свёрнутом Activity, notification вне смены. Они явно используют тестовые события, не затрагивают backend и не проверяют транспорт FCM.

```bash
cd mobile/driver_app/android
./gradlew app:assembleDebug app:assembleDebugAndroidTest
adb install -r ../build/app/outputs/apk/debug/app-debug.apk
adb install -r ../build/app/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb shell pm grant kg.fleethub.driver_app android.permission.POST_NOTIFICATIONS
adb shell appops set kg.fleethub.driver_app SYSTEM_ALERT_WINDOW allow
adb shell am instrument -w kg.fleethub.driver_app.test/androidx.test.runner.AndroidJUnitRunner
```

Не устанавливайте instrumentation APK пользователям. Для повторного теста реальной доставки используйте checklist выше с Firebase и Яндекс Про.
