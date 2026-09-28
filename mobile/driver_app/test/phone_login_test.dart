import 'dart:async';

import 'package:dio/dio.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:driver_app/core/phone_login.dart';
import 'package:flutter_test/flutter_test.dart';

class FakePhoneAuth implements PhoneAuthGateway {
  final sent = <void Function(String, int?)>[];
  final completed = <void Function(PhoneAuthCredential)>[];
  final failed = <void Function(FirebaseAuthException)>[];
  final timedOut = <void Function(String)>[];
  final phones = <String>[];
  final resends = <int?>[];
  int signIns = 0;
  PhoneAuthCredential? lastCredential;
  Future<String> Function()? signInAction;
  @override
  Future<void> requestCode({
    required String phone,
    int? resendToken,
    required void Function(String, int?) codeSent,
    required void Function(PhoneAuthCredential) completed,
    required void Function(FirebaseAuthException) failed,
    required void Function(String) timeout,
  }) async {
    phones.add(phone);
    resends.add(resendToken);
    sent.add(codeSent);
    this.completed.add(completed);
    this.failed.add(failed);
    timedOut.add(timeout);
  }

  @override
  Future<String> signIn(PhoneAuthCredential credential) async {
    signIns++;
    lastCredential = credential;
    return signInAction == null ? 'test-id-token' : await signInAction!();
  }
}

void main() {
  late FakePhoneAuth gateway;
  late PhoneLoginController login;
  late List<String> tokens;
  late Future<void> Function(String) exchange;
  setUp(() {
    gateway = FakePhoneAuth();
    tokens = [];
    exchange = (token) async {
      tokens.add(token);
    };
    login = PhoneLoginController(
      gateway: gateway,
      exchangeToken: (t) => exchange(t),
    );
  });
  tearDown(() => login.dispose());
  const number = '+15555550123';
  PhoneAuthCredential credential() => PhoneAuthProvider.credential(
    verificationId: 'session',
    smsCode: '654321',
  );
  Future<void> readyForCode() async {
    await login.request(number);
    gateway.sent.last('session', 42);
  }

  test(
    'request remains busy until Firebase callback, prevents duplicate requests',
    () async {
      await login.request('+1 (555) 555-0123');
      expect(login.busy, true);
      await login.request(number);
      expect(gateway.phones, [number]);
      gateway.sent.single('session', 42);
      expect(login.busy, false);
      expect(login.verificationId, 'session');
    },
  );
  test(
    'test code uses Firebase credentials and exchanges its real token',
    () async {
      await readyForCode();
      await login.submitCode('654321');
      expect(gateway.lastCredential!.verificationId, 'session');
      expect(gateway.lastCredential!.smsCode, '654321');
      expect(tokens, ['test-id-token']);
      expect(login.error, isNull);
    },
  );
  test('test auth skips Firebase and sends phone with entered code', () async {
    final credentials = <(String, String)>[];
    final testLogin = PhoneLoginController(
      gateway: gateway,
      exchangeToken: (_) async {},
      testAuthEnabled: true,
      testLogin: (phone, code) async => credentials.add((phone, code)),
    );
    addTearDown(testLogin.dispose);

    await testLogin.request(number);
    expect(testLogin.codeRequested, isTrue);
    expect(testLogin.busy, isFalse);
    expect(gateway.phones, isEmpty);

    await testLogin.submitCode('123456');
    expect(credentials, [(number, '123456')]);
    expect(gateway.signIns, 0);
    expect(testLogin.error, isNull);
  });
  test('manual and automatic verification cannot sign in twice', () async {
    await readyForCode();
    final token = Completer<String>();
    gateway.signInAction = () => token.future;
    final manual = login.submitCode('654321');
    gateway.completed.single(credential());
    await login.submitCode('654321');
    expect(gateway.signIns, 1);
    token.complete('token');
    await manual;
    gateway.completed.single(credential());
    expect(tokens, ['token']);
    expect(gateway.signIns, 1);
  });
  test(
    'late callbacks from changed number cannot replace verification session',
    () async {
      await login.request(number);
      login.changePhone();
      await login.request('+15555550124');
      gateway.sent[1]('new', 7);
      gateway.sent[0]('old', 6);
      gateway.failed[0](FirebaseAuthException(code: 'network-request-failed'));
      gateway.completed[0](credential());
      expect(login.verificationId, 'new');
      expect(login.error, isNull);
      expect(gateway.signIns, 0);
    },
  );
  test('resend uses Firebase resend token and ignores old callbacks', () async {
    await readyForCode();
    await login.request(number, resend: true);
    expect(gateway.resends, [null, 42]);
    expect(login.busy, true);
    gateway.sent.first('stale', 8);
    expect(login.verificationId, isNull);
    gateway.sent.last('new-session', 43);
    expect(login.verificationId, 'new-session');
  });
  test('auto retrieval timeout still permits manual confirmation', () async {
    await login.request(number);
    gateway.timedOut.single('session');
    expect(login.error, isNull);
    expect(login.busy, false);
    await login.submitCode('654321');
    expect(tokens.length, 1);
  });
  test(
    'Firebase network failure is distinct from wrong code and retry works',
    () async {
      await readyForCode();
      gateway.signInAction = () async =>
          throw FirebaseAuthException(code: 'network-request-failed');
      await login.submitCode('654321');
      expect(login.error, contains('network-request-failed'));
      expect(tokens, isEmpty);
      expect(login.verificationId, 'session');
      expect(login.busy, false);
      gateway.signInAction = null;
      await login.submitCode('654321');
      expect(tokens.length, 1);
    },
  );
  test(
    'code request failure releases busy with actionable Firebase error',
    () async {
      await login.request(number);
      gateway.failed.single(
        FirebaseAuthException(code: 'invalid-phone-number'),
      );
      expect(login.busy, false);
      expect(login.error, contains('корректный номер'));
    },
  );
  test(
    'wrong code does not get mislabeled as backend or network failure',
    () async {
      await readyForCode();
      gateway.signInAction = () async =>
          throw FirebaseAuthException(code: 'invalid-verification-code');
      await login.submitCode('654321');
      expect(login.error, startsWith('Неверный код'));
      expect(tokens, isEmpty);
    },
  );
  for (final status in [null, 401, 403, 503]) {
    test(
      'backend $status preserves verified token for retry without reusing OTP',
      () async {
        await readyForCode();
        final options = RequestOptions(path: '/auth/firebase');
        exchange = (_) async => throw DioException(
          requestOptions: options,
          response: status == null
              ? null
              : Response(requestOptions: options, statusCode: status),
        );
        await login.submitCode('654321');
        expect(login.numberVerified, true);
        expect(
          login.error,
          contains(status == 401 ? 'Firebase подтвердил' : 'Номер подтверждён'),
        );
        expect(gateway.signIns, 1);
        exchange = (token) async {
          tokens.add(token);
        };
        await login.submitCode('');
        expect(gateway.signIns, 1);
        expect(tokens, ['test-id-token']);
      },
    );
  }
  test('invalid code length never starts Firebase sign-in', () async {
    await readyForCode();
    await login.submitCode('123');
    expect(gateway.signIns, 0);
    expect(login.error, contains('шестизначный'));
  });
  test('changing number removes previously verified token', () async {
    await readyForCode();
    exchange = (_) async => throw StateError('backend down');
    await login.submitCode('654321');
    expect(login.numberVerified, true);
    login.changePhone();
    expect(login.numberVerified, false);
    expect(login.verificationId, isNull);
  });
}
