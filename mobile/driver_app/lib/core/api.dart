import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class FleetApi {
  final FlutterSecureStorage storage;
  final Dio dio;
  String? token;
  bool offline = false;
  void Function()? onUnauthorized;
  FleetApi({Dio? client, this.storage = const FlutterSecureStorage()})
    : dio =
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
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) {
          if (error.response?.statusCode == 401 &&
              !error.requestOptions.path.contains('/auth/firebase')) {
            onUnauthorized?.call();
          }
          handler.next(error);
        },
      ),
    );
  }
  Future<void> restore() async {
    token = await storage.read(key: 'jwt');
  }

  Future<void> login(String idToken) async {
    final response = await dio.post(
      '/auth/firebase',
      data: {'id_token': idToken},
    );
    token = response.data['access_token'];
    await storage.write(key: 'jwt', value: token);
  }

  Future<dynamic> get(String path) async {
    try {
      final response = await dio.get(path);

      await storage.write(key: 'cache:$path', value: jsonEncode(response.data));
      return response.data;
    } on DioException catch (e) {
      if (e.response == null) {
        offline = true;
        final cached = await storage.read(key: 'cache:$path');
        if (cached != null) {
          return jsonDecode(cached);
        }
      }
      rethrow;
    }
  }

  Future<void> clear() async {
    token = null;
    await storage.deleteAll();
  }
}

String errorMessage(Object error) {
  if (error is DioException) {
    return switch (error.response?.statusCode) {
      401 => 'Сессия истекла. Войдите снова.',
      403 => 'Номер не найден в парке. Обратитесь к диспетчеру.',
      404 => 'Данные не найдены.',
      429 => 'Слишком много запросов. Попробуйте позже.',
      503 => 'Данные Яндекс или сервис входа временно недоступны.',
      _ =>
        'Не удалось получить данные. Проверьте интернет и попробуйте ещё раз.',
    };
  }
  return 'Не удалось выполнить действие. Попробуйте ещё раз.';
}
