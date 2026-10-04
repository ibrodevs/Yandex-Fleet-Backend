import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:driver_app/core/api.dart';
import 'package:driver_app/core/state.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

const refreshData = <String, dynamic>{
  '/me': {'id': 'driver', 'first_name': 'Cached driver'},
  '/summary': {'active_orders': 0},
  '/vehicle': null,
  '/orders': <dynamic>[],
  '/settings': <String, dynamic>{},
};

// Manually settle requests in either order without timers or live HTTP/Firebase.
class Requests {
  final dio = Dio();
  final pending = <String, (RequestOptions, RequestInterceptorHandler)>{};
  final paths = <String>[];
  final waiters = <(int, Completer<void>)>[];
  Requests() {
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          paths.add(options.path);
          pending[options.path] = (options, handler);
          for (final waiter in waiters) {
            if (paths.length >= waiter.$1 && !waiter.$2.isCompleted) {
              waiter.$2.complete();
            }
          }
        },
      ),
    );
  }
  Future<void> waitFor(int count) {
    if (paths.length >= count) return Future.value();
    final done = Completer<void>();
    waiters.add((count, done));
    return done.future;
  }

  void success(String path, [dynamic data]) {
    final (options, handler) = pending.remove(path)!;
    handler.resolve(
      Response(requestOptions: options, statusCode: 200, data: data),
    );
  }

  void fail(
    String path, {
    int? status,
    DioExceptionType type = DioExceptionType.connectionTimeout,
  }) {
    final (options, handler) = pending.remove(path)!;
    handler.reject(
      DioException(
        requestOptions: options,
        type: status == null ? type : DioExceptionType.badResponse,
        response: status == null
            ? null
            : Response(requestOptions: options, statusCode: status),
      ),
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Requests requests;
  late FleetApi api;
  late AppState state;
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({
      for (final entry in refreshData.entries)
        'cache:${entry.key}': jsonEncode(entry.value),
      'cache:/probe': '{}',
    });
    requests = Requests();
    api = FleetApi(client: requests.dio)..token = 'session';
    state = AppState(api, false);
  });
  tearDown(() {
    state.dispose();
    api.dispose();
  });

  Future<void> offline() async {
    final count = requests.paths.length;
    final get = api.get('/probe');
    await requests.waitFor(count + 1);
    requests.fail('/probe');
    await get;
    expect(api.offline, isTrue);
  }

  for (final failureFirst in [true, false]) {
    test('mixed refresh stays online, failureFirst=$failureFirst', () async {
      final refresh = state.refresh();
      await requests.waitFor(5);
      expect(requests.paths.toSet(), refreshData.keys.toSet());
      if (failureFirst) requests.fail('/me');
      for (final e in refreshData.entries.where((e) => e.key != '/me')) {
        requests.success(e.key, e.value);
      }
      if (!failureFirst) requests.fail('/me');
      await refresh;
      expect(api.offline, isFalse);
      expect(state.driver['id'], 'driver');
      expect(state.error, isNull);
    });
  }

  test(
    'all transport failures use cache and mark offline only after settling',
    () async {
      final refresh = state.refresh();
      await requests.waitFor(5);
      for (final path in refreshData.keys.where((p) => p != '/settings')) {
        requests.fail(path);
      }
      await Future<void>.delayed(Duration.zero);
      expect(api.offline, isFalse);
      requests.fail('/settings');
      await refresh;
      expect(api.offline, isTrue);
      expect(state.driver['id'], 'driver');
      expect(state.error, isNull);
    },
  );

  test('profile is applied while orders request is still pending', () async {
    final profileLoaded = Completer<void>();
    state.addListener(() {
      if (state.driver['id'] == 'driver' && !profileLoaded.isCompleted) {
        profileLoaded.complete();
      }
    });

    final refresh = state.refresh();
    await requests.waitFor(5);
    requests.success('/me', {'id': 'driver', 'first_name': 'Fresh driver'});
    await profileLoaded.future;

    expect(state.driver['first_name'], 'Fresh driver');
    expect(requests.pending.containsKey('/orders'), isTrue);

    requests.fail('/summary', status: 503);
    requests.success('/vehicle', null);
    requests.success('/settings', {});
    requests.success('/orders', []);
    await refresh;

    expect(state.orders, isEmpty);
    expect(state.error, contains('временно недоступны'));
  });

  test(
    'rate limited orders use saved active and completed data, then recover',
    () async {
      const savedOrders = [
        {'id': 'ride', 'status': 'in_progress'},
        {'id': 'done', 'status': 'completed'},
      ];
      await api.storage.write(
        key: 'cache:/orders',
        value: jsonEncode(savedOrders),
      );
      final refresh = state.refresh();
      await requests.waitFor(5);
      for (final entry in refreshData.entries.where(
        (e) => e.key != '/orders',
      )) {
        requests.success(entry.key, entry.value);
      }
      requests.fail('/orders', status: 429);
      await refresh;

      expect(state.orders.map((o) => o.id), ['ride', 'done']);
      expect(state.orders.first.active, isTrue);
      expect(state.orders.last.history, isTrue);
      expect(state.ordersStale, isTrue);
      expect(state.ordersLoadFailed, isFalse);

      final next = state.refresh();
      await requests.waitFor(10);
      for (final entry in refreshData.entries) {
        requests.success(
          entry.key,
          entry.key == '/orders' ? savedOrders : entry.value,
        );
      }
      await next;
      expect(state.ordersStale, isFalse);
    },
  );

  test('uncached failed orders are reported as unavailable', () async {
    await api.storage.delete(key: 'cache:/orders');
    final refresh = state.refresh();
    await requests.waitFor(5);
    for (final entry in refreshData.entries.where((e) => e.key != '/orders')) {
      requests.success(entry.key, entry.value);
    }
    requests.fail('/orders', status: 429);
    await refresh;

    expect(state.orders, isEmpty);
    expect(state.ordersLoadFailed, isTrue);
    expect(state.error, contains('Слишком много запросов'));
  });

  test(
    'partial transport failure is reported accurately and retried',
    () async {
      state.dispose();
      state = AppState(
        api,
        false,
        retryInterval: const Duration(milliseconds: 100),
      );
      await api.storage.delete(key: 'cache:/me');
      final refresh = state.refresh();
      await requests.waitFor(5);
      requests.fail('/me');
      for (final entry in refreshData.entries.where((e) => e.key != '/me')) {
        requests.success(entry.key, entry.value);
      }
      await refresh;
      expect(api.backendUnavailable, isFalse);
      expect(state.error, contains('Часть данных не загрузилась'));

      await requests.waitFor(10).timeout(const Duration(seconds: 2));
      final recovered = Completer<void>();
      state.addListener(() {
        if (state.error == null && !recovered.isCompleted) recovered.complete();
      });
      for (final entry in refreshData.entries) {
        requests.success(entry.key, entry.value);
      }
      await recovered.future.timeout(const Duration(seconds: 2));
      expect(state.driver['id'], 'driver');
    },
  );

  test('GET retries a dropped connection once', () async {
    final request = api.get('/probe');
    await requests.waitFor(1);
    requests.fail('/probe', type: DioExceptionType.connectionError);
    await requests.waitFor(2).timeout(const Duration(seconds: 2));
    requests.success('/probe', {'ok': true});
    expect(await request, {'ok': true});
    expect(api.backendUnavailable, isFalse);
  });

  for (final testLogin in [false, true]) {
    test(
      '${testLogin ? 'test' : 'Firebase'} login notifies after JWT before refresh completes',
      () async {
        final signedInNotice = Completer<void>();
        state.addListener(() {
          if (state.signedIn && !signedInNotice.isCompleted) {
            signedInNotice.complete();
          }
        });

        final login = testLogin
            ? state.loginWithTestCredentials('+79022558511', '123456')
            : state.loginWithFirebaseToken('firebase-id-token');
        final loginPath = testLogin ? '/auth/test' : '/auth/firebase';
        await requests.waitFor(1);
        requests.success(loginPath, {'access_token': 'mobile-jwt'});
        await signedInNotice.future;
        await requests.waitFor(6);

        expect(state.signedIn, isTrue);
        expect(
          requests.paths,
          containsAll(['/me', '/summary', '/vehicle', '/orders', '/settings']),
        );

        for (final entry in refreshData.entries) {
          requests.success(entry.key, entry.value);
        }
        await login;
      },
    );
  }

  test('Firebase exchange waits for slow driver lookup and retries a lost connection', () async {
    final login = api.login('firebase-id-token');
    await requests.waitFor(1);
    expect(
      requests.pending['/auth/firebase']!.$1.receiveTimeout,
      const Duration(seconds: 75),
    );
    requests.fail('/auth/firebase', type: DioExceptionType.connectionError);
    await requests.waitFor(2);
    requests.success('/auth/firebase', {'access_token': 'mobile-jwt'});
    await login;
    expect(api.token, 'mobile-jwt');
    expect(api.backendUnavailable, isFalse);
    expect(requests.paths, ['/auth/firebase', '/auth/firebase']);
  });

  test('Firebase exchange does not retry rejected credentials', () async {
    final login = api.login('firebase-id-token');
    final assertion = expectLater(login, throwsA(isA<DioException>()));
    await requests.waitFor(1);
    requests.fail('/auth/firebase', status: 401);
    await assertion;
    expect(requests.paths, ['/auth/firebase']);
    expect(api.backendUnavailable, isFalse);
  });

  test('HTTP 503 clears offline and surfaces service error despite cached settings', () async {
    await offline();
    final refresh = state.refresh();
    await requests.waitFor(6);
    requests.fail('/settings', status: 503);
    for (final path in refreshData.keys.where((p) => p != '/settings')) {
      requests.fail(path);
    }
    await refresh;
    expect(api.offline, isFalse);
    expect(state.error, contains('временно недоступны'));
  });

  for (final status in [401, 403, 404, 429, 500, 502, 503]) {
    test('HTTP $status is reachable and never replaced with cache', () async {
      await offline();
      final get = api.get('/settings');
      final assertion = expectLater(
        get,
        throwsA(
          isA<DioException>().having(
            (e) => e.response?.statusCode,
            'status',
            status,
          ),
        ),
      );
      await requests.waitFor(2);
      requests.fail('/settings', status: status);
      await assertion;
      expect(api.offline, isFalse);
    });
  }

  test(
    'next successful refresh restores online state and updates data',
    () async {
      await offline();
      final refresh = state.refresh();
      await requests.waitFor(6);
      expect(api.offline, isTrue); // Starting a request alone is not evidence.
      for (final entry in refreshData.entries) {
        requests.success(
          entry.key,
          entry.key == '/me' ? {'id': 'fresh'} : entry.value,
        );
      }
      await refresh;
      expect(api.offline, isFalse);
      expect(state.driver['id'], 'fresh');
    },
  );

  test(
    'successful standalone settings restores online state and notifies UI',
    () async {
      await offline();
      var updates = 0;
      state.addListener(() => updates++);
      final get = api.get('/settings');
      await requests.waitFor(2);
      requests.success('/settings', {});
      await get;
      expect(api.offline, isFalse);
      expect(updates, 1);
    },
  );

  test(
    'successful device registration restores online state and notifies UI',
    () async {
      await offline();
      var updates = 0;
      state.addListener(() => updates++);
      final post = api.post('/devices', data: {'fcm_token': 'test'});
      await requests.waitFor(2);
      requests.success('/devices', {'device_id': 'device'});
      await post;
      expect(api.offline, isFalse);
      expect(updates, 1);
    },
  );

  test('test login posts phone and code then persists backend JWT', () async {
    final login = api.testLogin('+79022558511', '123456');
    await requests.waitFor(1);
    expect(requests.paths, ['/auth/test']);
    requests.success('/auth/test', {'access_token': 'mobile-jwt'});
    await login;

    expect(api.token, 'mobile-jwt');
    expect(await api.storage.read(key: 'jwt'), 'mobile-jwt');
  });

  test(
    'devices response survives late failures from overlapping refresh',
    () async {
      final refresh = state.refresh();
      final post = api.post('/devices');
      await requests.waitFor(6);
      requests.success('/devices', {});
      await post;
      for (final path in refreshData.keys) {
        requests.fail(path);
      }
      await refresh;
      expect(api.offline, isFalse);
    },
  );

  test('overlapping refresh calls share exactly five requests', () async {
    final first = state.refresh();
    final second = state.refresh();
    expect(identical(first, second), isTrue);
    await requests.waitFor(5);
    for (final entry in refreshData.entries) {
      requests.success(entry.key, entry.value);
    }
    await Future.wait([first, second]);
    expect(requests.paths.length, 5);
  });

  test('cancellation does not imply offline or return cached data', () async {
    final get = api.get('/settings');
    final assertion = expectLater(get, throwsA(isA<DioException>()));
    await requests.waitFor(1);
    requests.fail('/settings', type: DioExceptionType.cancel);
    await assertion;
    expect(api.offline, isFalse);
  });

  for (final type in [
    DioExceptionType.connectionError,
    DioExceptionType.connectionTimeout,
    DioExceptionType.sendTimeout,
    DioExceptionType.receiveTimeout,
    DioExceptionType.unknown,
  ]) {
    test('$type without response uses cache and marks offline', () async {
      final get = api.get('/settings');
      await requests.waitFor(1);
      requests.fail('/settings', type: type);
      if (type == DioExceptionType.connectionError) {
        await requests.waitFor(2).timeout(const Duration(seconds: 2));
        requests.fail('/settings', type: type);
      }
      expect(await get, isEmpty);
      expect(api.offline, isTrue);
    });
  }

  test(
    'certificate failure is surfaced instead of presenting cached data',
    () async {
      final get = api.get('/settings');
      final assertion = expectLater(get, throwsA(isA<DioException>()));
      await requests.waitFor(1);
      requests.fail('/settings', type: DioExceptionType.badCertificate);
      await assertion;
      expect(api.backendUnavailable, isFalse);
    },
  );

  test('transport error without cache is surfaced', () async {
    final get = api.get('/uncached');
    final assertion = expectLater(get, throwsA(isA<DioException>()));
    await requests.waitFor(1);
    requests.fail('/uncached');
    await assertion;
    expect(api.offline, isTrue);
  });
}
