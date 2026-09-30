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
  StreamSubscription<dynamic>? subscription;
  String? error;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    subscription = events.receiveBroadcastStream().listen(
      (_) => refresh(),
      onError: showError,
    );
    refresh();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) refresh();
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
    } catch (e) {
      showError(e);
    }
  }

  Future<void> copy() async {
    try {
      final text = await methods.invokeMethod<String>('getDebugLog');
      await Clipboard.setData(ClipboardData(text: text ?? ''));
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Журнал скопирован')));
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

  Widget row(String title, String key, {String? action}) {
    final enabled = status[key] == true;
    return Card(
      child: ListTile(
        title: Text(title),
        subtitle: Text(enabled ? 'Включено' : 'Выключено / недоступно'),
        leading: Icon(
          enabled ? Icons.check_circle : Icons.info_outline,
          color: enabled ? Colors.green : null,
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
        const Text(
          'Диагностический этап. Сервис читает доступные элементы экрана Yandex Pro. Обнаружение заказов и действия с ними ещё не включены: сначала нужно проверить дерево реального входящего предложения.',
        ),
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
                onPressed: copy,
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
