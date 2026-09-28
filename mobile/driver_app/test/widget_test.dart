import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:driver_app/app.dart';
import 'package:driver_app/core/api.dart';
import 'package:driver_app/core/models.dart';
import 'package:driver_app/core/state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
  });
  test('order model preserves unknown values and separates active/history', () {
    final order = FleetOrder({'id': 'a', 'status': 'assigned'});
    expect(order.active, true);
    expect(order.history, false);
    expect(order.price, '—');
    expect(order.pickup, '—');
    expect(FleetOrder({'status': 'unknown'}).history, false);
    expect(FleetOrder({'status': 'completed'}).history, true);
  });
  test(
    'notification parser accepts FCM string envelope, rejects invalid JSON',
    () {
      expect(
        FleetOrder.fromPush({
          'payload': jsonEncode({'order_id': '123', 'price': null}),
        })?.id,
        '123',
      );
      expect(FleetOrder.fromPush({'payload': 'broken'}), isNull);
      expect(FleetOrder.fromPush({}), isNull);
    },
  );
  test('overlay settings are copied without changing previous state', () {
    final previous = OverlaySettings();
    final next = previous.copy('sound', false);
    expect(previous.data['sound'], true);
    expect(next.data['sound'], false);
    expect(next.data['display_seconds'], 15);
  });
  test('auth restores token and clear removes cached personal data', () async {
    FlutterSecureStorage.setMockInitialValues({
      'jwt': 'token',
      'cache:/me': '{"id":"a"}',
    });
    final api = FleetApi();
    await api.restore();
    expect(api.token, 'token');
    await api.clear();
    expect(api.token, isNull);
    expect(await api.storage.read(key: 'cache:/me'), isNull);
  });
  test(
    'repository retains secure offline cache only for network failures',
    () async {
      FlutterSecureStorage.setMockInitialValues({
        'cache:/orders': '[{"id":"a"}]',
      });
      final dio = Dio();
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (o, h) => h.reject(
            DioException(
              requestOptions: o,
              type: DioExceptionType.connectionError,
            ),
          ),
        ),
      );
      final api = FleetApi(client: dio);
      expect((await api.get('/orders'))[0]['id'], 'a');
      expect(api.offline, true);
      final denied = Dio();
      denied.interceptors.add(
        InterceptorsWrapper(
          onRequest: (o, h) => h.reject(
            DioException(
              requestOptions: o,
              response: Response(requestOptions: o, statusCode: 403),
            ),
          ),
        ),
      );
      await expectLater(
        FleetApi(client: denied).get('/orders'),
        throwsA(isA<DioException>()),
      );
    },
  );
  testWidgets('login respects the configured authentication mode', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(home: LoginScreen(state: AppState(FleetApi(), false))),
    );
    expect(find.text('fleet hub'), findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -500));
    await tester.pumpAndSettle();
    final submit = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(submit.onPressed, testAuthEnabled ? isNotNull : isNull);
    expect(
      find.text(
        'Вход станет доступен после подключения Firebase владельцем парка.',
      ),
      testAuthEnabled ? findsNothing : findsOneWidget,
    );
  });
  testWidgets('order card has no unsupported actions', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: OrderCard(
            order: FleetOrder({'id': '1', 'status': 'assigned'}),
            tappable: false,
          ),
        ),
      ),
    );
    expect(find.text('Принять'), findsNothing);
    expect(find.text('Завершить'), findsNothing);
    expect(find.text('Назначен'), findsOneWidget);
  });
}
