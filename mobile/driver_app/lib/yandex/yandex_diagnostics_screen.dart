import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class YandexDiagnosticsScreen extends StatefulWidget {
  const YandexDiagnosticsScreen({super.key});
  @override
  State<YandexDiagnosticsScreen> createState() =>
      _YandexDiagnosticsScreenState();
}

class _YandexDiagnosticsScreenState extends State<YandexDiagnosticsScreen>
    with WidgetsBindingObserver {
  static const methods = MethodChannel('fleet/yandex/methods');
  static const events = EventChannel('fleet/yandex/events');
  Map<String, dynamic> status = {};
  String monitorLog = '';
  int logRequest = 0;
  StreamSubscription<dynamic>? subscription;
  String? error;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    subscription = events.receiveBroadcastStream().listen((event) {
      if (event is Map && event['event'] == 'debug_log') {
        loadMonitorLog();
      } else {
        refresh();
        loadMonitorLog();
      }
    }, onError: (Object e) {
      showError(e);
      methods.invokeMethod<void>('recordMonitorError', e.runtimeType.toString()).catchError((_) {});
    });
    refresh();
    loadMonitorLog();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      refresh();
      loadMonitorLog();
    }
  }

  void showError(Object e) {
    if (mounted) setState(() => error = 'Ошибка диагностики: $e');
  }

  Future<void> refresh() async {
    try {
      final value = await methods.invokeMapMethod<String, dynamic>(
        'getServiceStatus',
      );
      if (mounted) {
        setState(() {
          status = value ?? {};
          error = null;
        });
      }
    } catch (e) {
      showError(e);
    }
  }

  Future<void> invoke(String name, [Object? args]) async {
    try {
      await methods.invokeMethod<void>(name, args);
      await refresh();
      await loadMonitorLog();
    } catch (e) {
      showError(e);
    }
  }

  Future<void> loadMonitorLog() async {
    final request = ++logRequest;
    try {
      final value = await methods.invokeMethod<String>('getMonitorLog');
      if (mounted && request == logRequest) setState(() => monitorLog = value ?? '');
    } catch (e) {
      showError(e);
    }
  }

  Future<void> copyMonitorLog() async {
    try {
      final text = await methods.invokeMethod<String>('getMonitorLog');
      await Clipboard.setData(ClipboardData(text: text ?? ''));
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Логи мониторинга скопированы')));
      }
    } catch (e) {
      showError(e);
    }
  }

  Future<void> copyAccessibilityLog() async {
    try {
      final text = await methods.invokeMethod<String>('getDebugLog');
      await Clipboard.setData(ClipboardData(text: text ?? ''));
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Debug-log скопирован')));
      }
    } catch (e) {
      showError(e);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    subscription?.cancel();
    super.dispose();
  }

  Widget row(String title, String key, {String? action, bool fallback = false}) {
    final enabled = status[key] == true;
    final color = enabled ? Colors.green : (fallback ? Colors.amber : Colors.red);
    return Card(
      child: ListTile(
        title: Text(title),
        subtitle: Text(enabled ? 'Включено' : 'Выключено / недоступно'),
        leading: Icon(
          enabled ? Icons.check_circle : Icons.info_outline,
          color: color,
        ),
        trailing: !enabled && action != null
            ? TextButton(
                onPressed: () => invoke(action),
                child: const Text('Включить'),
              )
            : null,
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Интеграция с Yandex Pro')),
    body: ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text('Мониторинг входящих предложений Yandex Pro работает через доступ к уведомлениям. Fleet API проверяется отдельно на сервере. Доступные поля зависят от текста реального уведомления.'),
        const SizedBox(height: 16),
        row('Доступ к уведомлениям', 'notificationAccess', action: 'openNotificationAccessSettings'),
        row('Сервис мониторинга подключён', 'notificationListener'),
        row('Уведомления Fleet Hub', 'fleetNotifications', action: 'openAppNotificationSettings', fallback: status['overlay'] == true),
        row('Водитель привязан', 'driverLinked'),
        row('Мониторинг активен', 'monitoringActive'),
        row('Режим водителя', 'driverMode', fallback: true),
        row('Поверх других приложений', 'overlay', action: 'openOverlaySettings', fallback: true),
        row('Сервис виджета', 'overlayService', fallback: true),
        row('FCM зарегистрирован', 'fcmRegistered', fallback: true),
        OutlinedButton(
          onPressed: () async {
            await refresh();
            if (!mounted) return;
            final listenerReady = status['notificationAccess'] == true &&
                status['notificationListener'] == true && status['driverLinked'] == true &&
                status['monitoringActive'] == true;
            final overlayReady = status['driverMode'] == true && status['overlay'] == true &&
                status['overlayService'] == true;
            final fallbackReady = status['fleetNotifications'] == true;
            final message = !listenerReady
                ? 'Мониторинг недоступен: проверьте доступ к уведомлениям, вход водителя и активность мониторинга'
                : overlayReady
                    ? 'Мониторинг готов: виджет поверх приложений доступен'
                    : fallbackReady
                        ? 'Мониторинг частично готов: виджет недоступен, будет системное уведомление'
                        : 'Мониторинг недоступен: нет доступа к виджету и уведомлениям Fleet Hub';
            ScaffoldMessenger.of(this.context).showSnackBar(SnackBar(content: Text(
              message,
            )));
          },
          child: const Text('Проверить мониторинг'),
        ),
        SwitchListTile(
          title: const Text('Режим отладки мониторинга'),
          value: status['monitorDebug'] == true,
          onChanged: (v) => invoke('setMonitorDebug', v),
        ),
        if (status['monitorDebug'] == true) ...[
          const Text('Логи мониторинга'),
          Wrap(spacing: 8, children: [
            OutlinedButton(onPressed: copyMonitorLog, child: const Text('Копировать')),
            TextButton(onPressed: () => invoke('clearMonitorLog'), child: const Text('Очистить')),
            TextButton(onPressed: () => invoke('shareMonitorLog'), child: const Text('Сохранить')),
          ]),
          SelectableText(monitorLog.isEmpty ? 'Записей пока нет.' : monitorLog),
        ],
        const SizedBox(height: 16),
        Card(
          child: ListTile(
            title: const Text('Yandex Pro'),
            subtitle: Text(
              status['installed'] == true ? 'Установлен' : 'Не установлен',
            ),
          ),
        ),
        row(
          'Специальные возможности',
          'accessibility',
          action: 'openAccessibilitySettings',
        ),
        row(
          'Отображение поверх приложений',
          'overlay',
          action: 'openOverlaySettings',
        ),
        row('Сервис диагностики подключён', 'connected'),
        if (status['debugAvailable'] == true) ...[
          const SizedBox(height: 16),
          const Text(
            'Журнал может содержать адреса поездок. Включайте запись только на экране предложения. Данные хранятся в памяти и не отправляются на сервер. При выключении записи или остановке сервиса журнал очищается. Копирование переносит его в буфер обмена.',
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Записывать дерево Yandex Pro'),
            value: status['recording'] == true,
            onChanged: (v) => invoke('setDebugRecording', v),
          ),
          Wrap(
            spacing: 8,
            children: [
              OutlinedButton(
                onPressed: copyAccessibilityLog,
                child: const Text('Скопировать debug-log'),
              ),
              TextButton(
                onPressed: () => invoke('clearDebugLog'),
                child: const Text('Очистить журнал'),
              ),
            ],
          ),
        ] else
          const Text('Подробная запись доступна только в debug-сборке.'),
        const SizedBox(height: 16),
        Text(
          'Последнее событие Accessibility',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        SelectableText(
          status['lastEvent'] == null
              ? 'Событий пока нет. Откройте Yandex Pro после включения сервиса.'
              : const JsonEncoder.withIndent('  ').convert(status['lastEvent']),
        ),
        if (error != null) Text(error!),
        TextButton(onPressed: refresh, child: const Text('Обновить статус')),
      ],
    ),
  );
}
