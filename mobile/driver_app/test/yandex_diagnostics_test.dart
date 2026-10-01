import 'package:driver_app/yandex/yandex_diagnostics_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const methods = MethodChannel('fleet/yandex/methods');
  const events = MethodChannel('fleet/yandex/events');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  tearDown(() {
    messenger.setMockMethodCallHandler(methods, null);
    messenger.setMockMethodCallHandler(events, null);
  });
  testWidgets(
    'Absent Yandex and disconnected service are not reported as ready',
    (tester) async {
      messenger.setMockMethodCallHandler(events, (_) async => null);
      messenger.setMockMethodCallHandler(
        methods,
        (_) async => <String, dynamic>{
          'installed': false,
          'accessibility': false,
          'overlay': false,
          'connected': false,
          'debugAvailable': false,
        },
      );
      await tester.pumpWidget(
        const MaterialApp(home: YandexDiagnosticsScreen()),
      );
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('Не установлен'), 300);
      expect(find.text('Не установлен'), findsOneWidget);
      expect(find.text('Включить'), findsWidgets);
      expect(find.text('Записывать дерево Yandex Pro'), findsNothing);
      await tester.scrollUntilVisible(
        find.textContaining('Подробная запись доступна только'), 300);
      expect(
        find.textContaining('Подробная запись доступна только'),
        findsOneWidget,
      );
    },
  );
  testWidgets('Accessibility button opens the native settings method', (
    tester,
  ) async {
    final calls = <String>[];
    messenger.setMockMethodCallHandler(events, (_) async => null);
    messenger.setMockMethodCallHandler(methods, (call) async {
      calls.add(call.method);
      return call.method == 'getServiceStatus'
          ? <String, dynamic>{'debugAvailable': false}
          : null;
    });
    await tester.pumpWidget(const MaterialApp(home: YandexDiagnosticsScreen()));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Специальные возможности'), 300);
    final card = find.ancestor(of: find.text('Специальные возможности'), matching: find.byType(Card));
    await tester.tap(find.descendant(of: card, matching: find.text('Включить')));
    await tester.pumpAndSettle();
    expect(calls, contains('openAccessibilitySettings'));
  });

  testWidgets('Monitor and Accessibility copy buttons use separate logs', (tester) async {
    final calls = <String>[];
    messenger.setMockMethodCallHandler(events, (_) async => null);
    messenger.setMockMethodCallHandler(methods, (call) async {
      calls.add(call.method);
      switch (call.method) {
        case 'getServiceStatus':
          return <String, dynamic>{'monitorDebug': true, 'debugAvailable': true};
        case 'getMonitorLog':
          return 'monitor log';
        case 'getDebugLog':
          return 'accessibility log';
        default:
          return null;
      }
    });
    await tester.pumpWidget(const MaterialApp(home: YandexDiagnosticsScreen()));
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Копировать'), 300);
    await tester.tap(find.text('Копировать'));
    await tester.pumpAndSettle();
    expect(calls.last, 'getMonitorLog');
    for (var i = 0; i < 8 && find.text('Скопировать debug-log').evaluate().isEmpty; i++) {
      await tester.drag(find.byType(ListView), const Offset(0, -300));
      await tester.pumpAndSettle();
    }
    await tester.tap(find.text('Скопировать debug-log').first);
    await tester.pumpAndSettle();
    expect(calls.last, 'getDebugLog');
  });
}
