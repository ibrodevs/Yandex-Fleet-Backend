# Проверка 27 сентября 2026

- Flutter 3.47.2, Dart 3.13.2.
- `pytest -q`: **82 passed**. Исправлена подготовка одного существующего integration-теста: тестовые Yandex credentials теперь задаются явно; production-интеграция не менялась.
- `flutter analyze`: **No issues found**.
- `flutter test`: **7 passed**.
- Ruff по новым/изменённым Python-модулям: **passed**.
- `flutter build apk --release`: **успешно**, примерно 55 MB.
- `flutter build appbundle --release`: **успешно**, примерно 54.5 MB.
- Android 15 / API 35, Google APIs ARM64 emulator: **3 instrumentation tests passed**. Локальный overlay и закрытие; notification вне смены; background service → overlay поверх Settings → закрытие → повтор не появляется.
- Release APK установлен и запущен на эмуляторе. Экран входа осмотрен, без обрезанного текста и ошибок AndroidRuntime.
- Скриншоты: [экран входа](login.png), [локальная тестовая карточка](overlay-example.png). Тестовая карточка содержит только явно помеченный пример.

## Не подтверждено и требует владельца проекта

- Firebase Phone Auth с реальным номером и поиск реального водителя.
- Развёртывание новых mobile routes и worker на production.
- Реальная FCM доставка, обновление токена при длительной фоновой работе.
- Overlay именно поверх установленного Яндекс Про, физические телефоны и ограничения производителей.
- iOS сборка, подпись и APNs.
- Подпись владельца для Google Play: текущие APK/AAB подписаны debug key, хотя собраны в release mode.

Firebase конфигурация не предоставлена. Ни SMS, ни реальные push, ни deployment не выполнялись. Это не полный production acceptance из ТЗ. Пошаговая настройка: [MOBILE_SETUP.md](../MOBILE_SETUP.md).
