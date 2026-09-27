import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api.dart';
import 'models.dart';

final appStateProvider = Provider<AppState>(
  (ref) => throw UnimplementedError(),
);
const overlayChannel = MethodChannel('fleet/overlay');

class AppState extends ChangeNotifier {
  final FleetApi api;
  final bool firebaseReady;
  bool ready = false, busy = false, driverMode = false;
  String? error;
  Map<String, dynamic> driver = {}, summary = {}, vehicle = {};
  List<FleetOrder> orders = [];
  OverlaySettings settings = OverlaySettings();
  final List<StreamSubscription<dynamic>> _subscriptions = [];
  void Function(String)? openOrder;
  AppState(this.api, this.firebaseReady);
  bool get signedIn => api.token != null;
  Future<void> init() async {
    api.onUnauthorized = () {
      unawaited(logout(remote: false));
    };
    await api.restore();
    if (Platform.isAndroid) {
      overlayChannel.setMethodCallHandler((call) async {
        if (call.method == 'openOrder') {
          openOrder?.call(call.arguments.toString());
        }
      });
    }
    _subscriptions.add(
      Connectivity().onConnectivityChanged.listen((result) {
        if (signedIn &&
            api.offline &&
            !result.contains(ConnectivityResult.none)) {
          refresh();
        }
      }),
    );
    if (signedIn) {
      await refresh();
    }
    ready = true;
    notifyListeners();
    if (signedIn) {
      await registerPush();
    }
  }

  Future<void> authenticate(PhoneAuthCredential credential) async {
    busy = true;
    error = null;
    notifyListeners();
    try {
      final result = await FirebaseAuth.instance.signInWithCredential(
        credential,
      );
      final token = await result.user!.getIdToken(true);
      await api.login(token!);
      await refresh();
      await registerPush();
    } catch (e) {
      error = errorMessage(e);
      rethrow;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> refresh() async {
    if (!signedIn) {
      return;
    }
    try {
      api.offline = false;
      final values = await Future.wait(
        ['/me', '/summary', '/vehicle', '/orders', '/settings'].map(api.get),
      );
      if (!signedIn) {
        return;
      }
      driver = Map<String, dynamic>.from(values[0]);
      summary = Map<String, dynamic>.from(values[1] ?? {});
      vehicle = Map<String, dynamic>.from(values[2] ?? {});
      orders = (values[3] as List)
          .map((o) => FleetOrder(Map<String, dynamic>.from(o)))
          .toList();
      settings = OverlaySettings(Map<String, dynamic>.from(values[4]));
      if (Platform.isAndroid) {
        await overlayChannel.invokeMethod(
          'setSession',
          driver['id']?.toString(),
        );
        await overlayChannel.invokeMethod('setSettings', settings.data);
        driverMode =
            await overlayChannel.invokeMethod<bool>('getDriverMode') ?? false;
      }
      error = null;
    } catch (e) {
      error = errorMessage(e);
    }
    notifyListeners();
  }

  Future<void> registerPush() async {
    if (!firebaseReady || !signedIn) {
      return;
    }
    try {
      await FirebaseMessaging.instance.requestPermission();
      await FirebaseMessaging.instance
          .setForegroundNotificationPresentationOptions(
            alert: true,
            badge: true,
            sound: true,
          );
      Future<void> register(String? token) async {
        if (token == null || !signedIn) {
          return;
        }
        var id = await api.storage.read(key: 'device_id');
        id ??= List.generate(
          24,
          (_) => Random.secure().nextInt(256).toRadixString(16).padLeft(2, '0'),
        ).join();
        await api.storage.write(key: 'device_id', value: id);
        await api.dio.post(
          '/devices',
          data: {
            'fcm_token': token,
            'platform': Platform.isAndroid ? 'android' : 'ios',
            'device_id': id,
          },
        );
      }

      await register(await FirebaseMessaging.instance.getToken());
      if (_subscriptions.length == 1) {
        _subscriptions.add(
          FirebaseMessaging.instance.onTokenRefresh.listen((t) async {
            try {
              await register(t);
            } catch (_) {}
          }),
        );
        _subscriptions.add(
          FirebaseMessaging.onMessage.listen((m) {
            refresh();
          }),
        );
        _subscriptions.add(
          FirebaseMessaging.onMessageOpenedApp.listen((m) {
            final order = FleetOrder.fromPush(m.data);
            if (order != null) {
              openOrder?.call(order.id);
            }
          }),
        );
      }
      final initial = await FirebaseMessaging.instance.getInitialMessage();
      if (initial != null) {
        final order = FleetOrder.fromPush(initial.data);
        if (order != null) {
          openOrder?.call(order.id);
        }
      }
      if (Platform.isAndroid) {
        final id = await overlayChannel.invokeMethod<String>('initialOrder');
        if (id != null) {
          openOrder?.call(id);
        }
      }
    } catch (_) {
      error = 'Не удалось зарегистрировать уведомления. Повторите обновление.';
      notifyListeners();
    }
  }

  Future<void> saveSettings(OverlaySettings next) async {
    await api.dio.put('/settings', data: next.data);
    settings = next;
    if (Platform.isAndroid) {
      await overlayChannel.invokeMethod('setSettings', settings.data);
    }
    notifyListeners();
  }

  Future<void> setMode(bool enabled) async {
    if (!Platform.isAndroid) {
      return;
    }
    await overlayChannel.invokeMethod('setDriverMode', enabled);
    driverMode = enabled;
    notifyListeners();
  }

  Future<void> logout({bool remote = true}) async {
    if (remote && signedIn) {
      await api.dio.post('/auth/logout');
    }
    if (Platform.isAndroid) {
      await overlayChannel.invokeMethod('setDriverMode', false);
      await overlayChannel.invokeMethod('clearSession');
    }
    await api.clear();
    if (firebaseReady) {
      await FirebaseAuth.instance.signOut();
    }
    driver = {};
    orders = [];
    vehicle = {};
    summary = {};
    driverMode = false;
    notifyListeners();
  }

  @override
  void dispose() {
    for (final s in _subscriptions) {
      s.cancel();
    }
    super.dispose();
  }
}
