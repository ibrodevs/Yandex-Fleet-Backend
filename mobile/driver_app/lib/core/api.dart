import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class FleetApi extends ChangeNotifier {
  final FlutterSecureStorage storage;
  final Dio _dio;
  String? token;
  bool _offline = false;
  // This means requests could not reach this backend; it does not prove that
  // the phone has no internet connection.
  bool get offline => _offline;
  bool get backendUnavailable => _offline;
  int _pendingRequests = 0;
  bool _waveHasResponse = false;
  bool _waveHasTransportFailure = false;
  void Function()? onUnauthorized;
  FleetApi({Dio? client, this.storage = const FlutterSecureStorage()})
    : _dio =
          client ??
          Dio(
            BaseOptions(
              baseUrl: const String.fromEnvironment(
                'API_BASE_URL',
                defaultValue: 'https://yandexfeetbackend21.pythonanywhere.com/api/v1/mobile',
              ),
              connectTimeout: const Duration(seconds: 15),
              receiveTimeout: const Duration(seconds: 25),
            ),
          ) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) {
          if (error.response?.statusCode == 401 &&
              !error.requestOptions.path.contains('/auth/firebase') &&
              !error.requestOptions.path.contains('/auth/test')) {
            onUnauthorized?.call();
          }
          handler.next(error);
        },
      ),
    );
  }
  void _setOffline(bool value) {
    if (_offline == value) return;
    _offline = value;
    notifyListeners();
  }

  static bool _isTransportFailure(DioException error) =>
      error.response == null &&
      error.type != DioExceptionType.cancel &&
      error.type != DioExceptionType.badResponse &&
      error.type != DioExceptionType.badCertificate &&
      (error.type != DioExceptionType.unknown ||
          error.error == null ||
          error.error is IOException);

  static void _trace(String message) {
    // Debug diagnostics contain only method/path/outcome, never headers or bodies.
    if (kDebugMode) debugPrint('[FleetApi] $message');
  }

  Future<Response<dynamic>> _request(
    String method,
    String path,
    Future<Response<dynamic>> Function() send,
  ) async {
    if (_pendingRequests++ == 0) {
      _waveHasResponse = false;
      _waveHasTransportFailure = false;
    }
    final timer = Stopwatch()..start();
    _trace('$method $path -> started');
    try {
      final response = await send();
      _waveHasResponse = true;
      _setOffline(false);
      _trace(
        '$method $path -> HTTP ${response.statusCode} (${timer.elapsedMilliseconds} ms)',
      );
      return response;
    } on DioException catch (error) {
      if (error.response != null) {
        // An HTTP error still proves that the backend is reachable.
        _waveHasResponse = true;
        _setOffline(false);
      } else if (_isTransportFailure(error)) {
        _waveHasTransportFailure = true;
      }
      _trace(
        '$method $path -> ${error.response?.statusCode ?? error.type.name} (${timer.elapsedMilliseconds} ms)',
      );
      rethrow;
    } finally {
      // Decide only after every overlapping request has settled. A later timeout
      // cannot overwrite a confirmed HTTP response from this request group.
      if (--_pendingRequests == 0 &&
          !_waveHasResponse &&
          _waveHasTransportFailure) {
        _setOffline(true);
      }
    }
  }

  Future<Response<dynamic>> post(String path, {Object? data}) =>
      _request('POST', path, () => _dio.post(path, data: data));

  Future<Response<dynamic>> put(String path, {Object? data}) =>
      _request('PUT', path, () => _dio.put(path, data: data));

  Future<void> restore() async {
    token = await storage.read(key: 'jwt');
  }

  Future<void> login(String idToken) async {
    Future<Response<dynamic>> exchange() => _request(
      'POST',
      '/auth/firebase',
      () => _dio.post(
        '/auth/firebase',
        data: {'id_token': idToken},
        // Driver lookup can wait for three 15-second Yandex attempts plus
        // backoff. The normal 25-second timeout interrupted valid logins.
        options: Options(receiveTimeout: const Duration(seconds: 75)),
      ),
    );
    late final Response<dynamic> response;
    try {
      response = await exchange();
    } on DioException catch (error) {
      if (error.response != null ||
          (error.type != DioExceptionType.connectionError &&
              error.type != DioExceptionType.connectionTimeout)) {
        rethrow;
      }
      await Future<void>.delayed(const Duration(milliseconds: 500));
      response = await exchange();
    }
    final accessToken = response.data['access_token'] as String;
    await storage.write(key: 'jwt', value: accessToken);
    token = accessToken;
  }

  Future<void> testLogin(String phone, String code) async {
    final response = await post(
      '/auth/test',
      data: {'phone': phone, 'code': code},
    );
    final accessToken = response.data['access_token'] as String;
    await storage.write(key: 'jwt', value: accessToken);
    token = accessToken;
  }

  Future<dynamic> get(String path, {void Function()? onCache}) async {
    try {
      Future<Response<dynamic>> fetch() =>
          _request('GET', path, () => _dio.get(path));
      late final Response<dynamic> response;
      try {
        response = await fetch();
      } on DioException catch (e) {
        if (e.response != null || e.type != DioExceptionType.connectionError) {
          rethrow;
        }
        // A VPN route change can invalidate a reused socket. A GET is safe to
        // resend once after the adapter opens a new connection.
        await Future<void>.delayed(const Duration(milliseconds: 400));
        response = await fetch();
      }

      await storage.write(key: 'cache:$path', value: jsonEncode(response.data));
      return response.data;
    } on DioException catch (e) {
      final recoverableServerError =
          path == '/orders' &&
          {429, 500, 502, 503, 504}.contains(e.response?.statusCode);
      if (_isTransportFailure(e) || recoverableServerError) {
        final cached = await storage.read(key: 'cache:$path');
        if (cached != null) {
          _trace('GET $path -> cache');
          onCache?.call();
          return jsonDecode(cached);
        }
      }
      rethrow;
    }
  }

  Future<void> clear() async {
    token = null;
    await storage.deleteAll();
    _setOffline(false);
  }
}

String errorMessage(Object error) {
  if (error is DioException) {
    if (error.response == null) {
      return error.type == DioExceptionType.badCertificate
          ? 'Не удалось установить защищённое соединение с сервером.'
          : 'Не удалось связаться с сервером. Попробуйте ещё раз.';
    }
    return switch (error.response?.statusCode) {
      401 => 'Сессия истекла. Войдите снова.',
      403 => 'Номер не найден в парке. Обратитесь к диспетчеру.',
      404 => 'Данные не найдены.',
      429 => 'Слишком много запросов. Попробуйте позже.',
      500 || 502 || 504 => 'Ошибка сервера. Попробуйте ещё раз позже.',
      503 => 'Данные Яндекс или сервис входа временно недоступны.',
      _ => 'Не удалось получить данные с сервера. Попробуйте ещё раз.',
    };
  }
  return 'Не удалось выполнить действие. Попробуйте ещё раз.';
}
