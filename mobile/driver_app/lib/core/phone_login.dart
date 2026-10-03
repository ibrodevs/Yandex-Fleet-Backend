import 'dart:async';

import 'package:dio/dio.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';

abstract class PhoneAuthGateway {
  Future<void> requestCode({
    required String phone,
    int? resendToken,
    required void Function(String, int?) codeSent,
    required void Function(PhoneAuthCredential) completed,
    required void Function(FirebaseAuthException) failed,
    required void Function(String) timeout,
  });
  Future<String> signIn(PhoneAuthCredential credential);
}

class FirebasePhoneAuthGateway implements PhoneAuthGateway {
  @override
  Future<void> requestCode({
    required String phone,
    int? resendToken,
    required void Function(String, int?) codeSent,
    required void Function(PhoneAuthCredential) completed,
    required void Function(FirebaseAuthException) failed,
    required void Function(String) timeout,
  }) => FirebaseAuth.instance.verifyPhoneNumber(
    phoneNumber: phone,
    forceResendingToken: resendToken,
    verificationCompleted: completed,
    verificationFailed: failed,
    codeSent: codeSent,
    codeAutoRetrievalTimeout: timeout,
  );

  @override
  Future<String> signIn(PhoneAuthCredential credential) async {
    final result = await FirebaseAuth.instance.signInWithCredential(credential);
    // Sign-in already obtained a fresh ID token. Do not force a second network refresh.
    final token = await result.user?.getIdToken();
    if (token == null || token.isEmpty) {
      throw FirebaseAuthException(code: 'missing-id-token');
    }
    return token;
  }
}

String phoneAuthError(Object error, {required bool backend}) {
  if (error is FirebaseAuthException) {
    return switch (error.code) {
      'network-request-failed' => 'Не удалось связаться с Firebase для проверки кода. Проверьте доступ к сервисам Google и повторите попытку. [Firebase: network-request-failed]',
      'invalid-verification-code' => 'Неверный код. Для тестового номера введите фиксированный код из Firebase Console.',
      'invalid-phone-number' => 'Введите корректный номер с кодом страны.',
      'session-expired' || 'invalid-verification-id' =>
        'Сессия подтверждения истекла. Запросите новый код.',
      'too-many-requests' =>
        'Firebase ограничил число попыток. Подождите перед повтором.',
      'operation-not-allowed' =>
        'В Firebase не разрешён вход по телефону или регион этого номера.',
      'app-not-authorized' ||
      'invalid-app-credential' ||
      'missing-client-identifier' =>
        'Firebase не подтвердил Android-приложение. Проверьте package name, SHA-1/SHA-256 и настройки API key. [Firebase: ${error.code}]',
      _ => 'Не удалось подтвердить номер в Firebase. [Firebase: ${error.code}]',
    };
  }
  if (backend && error is DioException) {
    return switch (error.response?.statusCode) {
      401 => 'Firebase подтвердил номер, но backend отклонил ID token. Проверьте Firebase project на сервере. [Backend: 401]',
      403 => 'Номер подтверждён Firebase, но водитель с таким номером не найден в парке. [Backend: 403]',
      503 => 'Номер подтверждён Firebase, но сервис входа backend временно недоступен. [Backend: 503]',
      504 => 'Номер подтверждён Firebase, но сервер не успел завершить вход. Повторите вход без нового кода. [Backend: 504]',
      null =>
        error.type == DioExceptionType.badCertificate
            ? 'Номер подтверждён Firebase. Не удалось установить защищённое соединение с сервером. Повторите вход без нового кода.'
            : error.type == DioExceptionType.receiveTimeout
            ? 'Номер подтверждён Firebase. Сервер слишком долго отвечает. Повторите вход без нового кода.'
            : 'Номер подтверждён Firebase. Не удалось связаться с сервером. Повторите вход без нового кода.',
      _ =>
        'Номер подтверждён Firebase. Ошибка backend: HTTP ${error.response?.statusCode}.',
    };
  }
  return backend
      ? 'Номер подтверждён Firebase. Не удалось завершить вход на backend.'
      : 'Не удалось выполнить проверку Firebase. Повторите попытку.';
}

class PhoneLoginController extends ChangeNotifier {
  final PhoneAuthGateway gateway;
  final Future<void> Function(String) exchangeToken;
  final bool testAuthEnabled;
  final Future<void> Function(String, String)? testLogin;
  PhoneLoginController({
    required this.gateway,
    required this.exchangeToken,
    this.testAuthEnabled = false,
    this.testLogin,
  });

  String? verificationId, error;
  String? _phone, _idToken;
  bool _testCodeRequested = false;
  int? _resendToken;
  int _generation = 0;
  bool busy = false,
      _disposed = false,
      _authenticating = false,
      _finished = false;
  Timer? _requestTimer;
  bool get numberVerified => _idToken != null;
  bool get codeRequested =>
      testAuthEnabled ? _testCodeRequested : verificationId != null;
  bool _current(int generation) =>
      !_disposed && generation == _generation && !_finished;
  void _changed() {
    if (!_disposed) notifyListeners();
  }

  Future<void> request(String input, {bool resend = false}) async {
    if (busy) return;
    final number = input.replaceAll(RegExp(r'[\s()-]'), '');
    if (!RegExp(r'^\+[1-9]\d{6,14}$').hasMatch(number)) {
      error = 'Введите номер с кодом страны, например +7 или +996.';
      _changed();
      return;
    }
    final token = resend && _phone == number ? _resendToken : null;
    final generation = ++_generation;
    _phone = number;
    _idToken = null;
    verificationId = null;
    _testCodeRequested = false;
    error = null;
    if (testAuthEnabled) {
      _testCodeRequested = true;
      busy = false;
      _finished = false;
      _changed();
      return;
    }
    busy = true;
    _finished = false;
    _changed();
    _requestTimer?.cancel();
    _requestTimer = Timer(const Duration(seconds: 90), () {
      if (_current(generation) && verificationId == null && !_authenticating) {
        ++_generation;
        busy = false;
        error = 'Firebase не ответил на запрос кода. Повторите попытку.';
        _changed();
      }
    });
    void failed(Object failure) {
      if (!_current(generation) || _authenticating || numberVerified) return;
      _requestTimer?.cancel();
      busy = false;
      error = phoneAuthError(failure, backend: false);
      _changed();
    }

    try {
      await gateway.requestCode(
        phone: number,
        resendToken: token,
        codeSent: (id, resendToken) {
          if (!_current(generation) || _authenticating || numberVerified) {
            return;
          }
          _requestTimer?.cancel();
          verificationId = id;
          _resendToken = resendToken;
          busy = false;
          error = null;
          _changed();
        },
        completed: (credential) {
          if (_current(generation)) {
            unawaited(_authenticate(credential, generation));
          }
        },
        failed: failed,
        timeout: (id) {
          if (!_current(generation) || _authenticating || numberVerified) {
            return;
          }
          _requestTimer?.cancel();
          // Auto-retrieval timeout does not invalidate the manually entered code.
          verificationId ??= id;
          busy = false;
          _changed();
        },
      );
      // verifyPhoneNumber returning only means listeners are registered, not code sent.
    } catch (failure) {
      failed(failure);
    }
  }

  Future<void> submitCode(String code) async {
    if (busy || _finished) return;
    if (testAuthEnabled) {
      final trimmedCode = code.trim();
      if (!RegExp(r'^\d{6}$').hasMatch(trimmedCode)) {
        error = 'Введите шестизначный код.';
        _changed();
        return;
      }
      await _authenticateTest(trimmedCode, _generation);
      return;
    }
    if (_idToken != null) {
      await _authenticate(null, _generation);
      return;
    }
    final id = verificationId;
    if (id == null) return;
    if (!RegExp(r'^\d{6}$').hasMatch(code.trim())) {
      error = 'Введите шестизначный код.';
      _changed();
      return;
    }
    await _authenticate(
      PhoneAuthProvider.credential(verificationId: id, smsCode: code.trim()),
      _generation,
    );
  }

  Future<void> _authenticateTest(String code, int generation) async {
    if (!_current(generation) || _authenticating) return;
    _authenticating = true;
    busy = true;
    error = null;
    _changed();
    try {
      await testLogin!(_phone!, code);
      if (_current(generation)) _finished = true;
    } catch (failure) {
      if (_current(generation)) {
        if (failure is DioException) {
          final status = failure.response?.statusCode;
          error = switch (status) {
            401 => 'Неверный номер или тестовый код.',
            403 => 'Водитель с этим номером не найден в парке.',
            404 => 'Тестовый вход отключён на backend.',
            503 => 'Backend или Яндекс временно недоступен.',
            null => 'Не удалось связаться с сервером. Повторите вход.',
            _ => 'Ошибка backend: HTTP $status.',
          };
        } else {
          error = 'Не удалось выполнить тестовый вход.';
        }
      }
    } finally {
      _authenticating = false;
      if (!_disposed && generation == _generation) {
        busy = false;
        _changed();
      }
    }
  }

  Future<void> _authenticate(
    PhoneAuthCredential? credential,
    int generation,
  ) async {
    if (!_current(generation) || _authenticating) return;
    _authenticating = true;
    busy = true;
    error = null;
    _requestTimer?.cancel();
    _changed();
    var backend = _idToken != null;
    try {
      _idToken ??= await gateway.signIn(credential!);
      if (!_current(generation)) return;
      backend = true;
      await exchangeToken(_idToken!);
      _finished = true;
      _idToken = null;
    } catch (failure) {
      if (_current(generation)) {
        error = phoneAuthError(failure, backend: backend);
        if (kDebugMode) {
          final code = failure is FirebaseAuthException
              ? failure.code
              : failure is DioException
              ? failure.response?.statusCode ?? failure.type.name
              : failure.runtimeType;
          debugPrint(
            '[AUTH] stage=${backend ? "backend" : "firebase"} code=$code',
          );
        }
      }
    } finally {
      _authenticating = false;
      if (!_disposed && generation == _generation) {
        busy = false;
        _changed();
      }
    }
  }

  void changePhone() {
    if (_authenticating) return;
    ++_generation;
    _requestTimer?.cancel();
    verificationId = null;
    _idToken = null;
    _phone = null;
    _testCodeRequested = false;
    _resendToken = null;
    busy = false;
    error = null;
    _finished = false;
    _changed();
  }

  @override
  void dispose() {
    _disposed = true;
    ++_generation;
    _idToken = null;
    _requestTimer?.cancel();
    super.dispose();
  }
}
