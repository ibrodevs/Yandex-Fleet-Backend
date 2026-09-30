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
      expect(find.text('Не установлен'), findsOneWidget);
      expect(find.text('Включить'), findsNWidgets(2));
      expect(find.text('Записывать дерево Yandex Pro'), findsNothing);
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
    await tester.tap(find.text('Включить').first);
    await tester.pumpAndSettle();
    expect(calls, contains('openAccessibilitySettings'));
  });
}
