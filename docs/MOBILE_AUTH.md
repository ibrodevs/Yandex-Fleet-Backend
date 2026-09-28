# Проверка входа Firebase на Android

Поток приложения: `verifyPhoneNumber` → callback с verificationId → `signInWithCredential` → `getIdToken()` → POST `/api/v1/mobile/auth/firebase`.

`verifyPhoneNumber` завершает Future после регистрации callbacks, а не после отправки кода. Контроллер `lib/core/phone_login.dart` ждёт callbacks, блокирует повторный запрос и вход, игнорирует callbacks старого номера/повторной отправки. Таймаут автоматического чтения SMS не запрещает ввод кода вручную. Повторная отправка использует выданный Firebase resend token.

После успешной проверки Firebase ID token временно хранится в памяти текущего экрана. Если backend недоступен, кнопка «Повторить вход» повторяет обмен токена, не использует уже принятый OTP повторно. При смене номера или закрытии экрана токен удаляется из контроллера. JWT backend записывается в secure storage до изменения состояния авторизации.

## Тестовые номера

Используйте номер и фиксированный шестизначный код, добавленные в **Authentication → Sign-in method → Phone → Phone numbers for testing** того же Firebase project, что указан в Android `google-services.json`. В исходниках нет тестовых номеров, обхода OTP, отключения проверки приложения или TLS. В обычном потоке используйте Console-код вместо SMS-кода.

Подтверждение тестового номера в Firebase не создаёт водителя в Yandex Fleet. После успешного Firebase-входа backend может вернуть 403, если этого номера нет в парке. Приложение сообщает это отдельно от ошибки кода или сети.

Источники: [Flutter Phone Auth](https://firebase.google.com/docs/auth/flutter/phone-auth), [Android Phone Auth и тестовые номера](https://firebase.google.com/docs/auth/android/phone-auth).

## Разделение ошибок

- `Firebase: network-request-failed`: SDK не завершил запрос к Google. Доступность нашего backend не доказывает доступность Firebase.
- `invalid-verification-code`: Firebase отклонил код.
- `session-expired`: запросите новый код.
- `Backend: 401`: сервер отклонил Firebase ID token; проверьте проект Firebase Admin и проверку токена.
- `Backend: 403`: подтверждённый номер не найден в парке.
- `Backend: 503`: серверный сервис авторизации/Yandex временно недоступен.

В debug-логах AUTH выводятся только этап и код ошибки, без OTP, ID tokens и содержимого исключений.

## DNS эмулятора

Если Android сообщает `UnknownHostException` / `unknown host` для `securetoken.googleapis.com` или `identitytoolkit.googleapis.com`, сначала восстановите доступ эмулятора к Google. Проверка:

```bash
adb shell ping -c 1 -W 2 securetoken.googleapis.com
```

`unknown host` указывает на проблему разрешения имени. Отсутствие ICMP-ответа само по себе не доказывает недоступность HTTPS.

Закройте работающий эмулятор и выполните холодный запуск с явными DNS, сохраняя данные AVD (подставьте имя из `emulator -list-avds`):

```bash
"$HOME/Library/Android/sdk/emulator/emulator" -avd Pixel_7 \
  -dns-server 8.8.8.8,1.1.1.1 -no-snapshot-load -no-snapshot-save
```

Дождитесь `adb shell getprop sys.boot_completed` → `1`. Эта настройка относится к запуску эмулятора, не изменяет DNS физического телефона и не подменяет адреса Google внутри приложения. Если сеть блокирует публичные DNS, используйте разрешённый и доступный DNS вашей сети.

## Проверки

```bash
cd mobile/driver_app
flutter test
flutter analyze
```

`test/phone_login_test.dart` проверяет callbacks, блокировку повторных попыток, resend, восстановление после сетевой ошибки, разделение ошибок и повтор backend-входа без повторного OTP. Firebase в unit-тестах заменяется контролируемым gateway; это не сетевой acceptance test.

Опциональный Android instrumentation-тест `FirebasePhoneAuthAcceptanceTest` использует настоящий Firebase SDK и Google endpoints, подтверждает вымышленный Console-номер и получает ID token. Он не вызывает backend. Номер и код передаются только через runner arguments `testPhoneNumber` / `testSmsCode`, не хранятся в репозитории. Без этих аргументов тест пропускается. После проверки тест завершает Firebase-сессию; запускайте на тестовом эмуляторе. Не передавайте в этот тест реальные SMS-коды.
