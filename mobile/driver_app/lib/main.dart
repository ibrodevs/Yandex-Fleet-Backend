import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/api.dart';
import 'core/state.dart';
import 'app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  bool firebaseReady = false;
  try {
    await Firebase.initializeApp();
    firebaseReady = true;
    debugPrint('[FIREBASE] initializeApp OK');
  } catch (e, stack) {
    debugPrint('[FIREBASE] initializeApp FAILED: $e');
    debugPrintStack(stackTrace: stack);
  }
  final state = AppState(FleetApi(), firebaseReady);
  runApp(
    ProviderScope(
      overrides: [appStateProvider.overrideWithValue(state)],
      child: Consumer(
        builder: (context, ref, child) =>
            FleetApp(state: ref.watch(appStateProvider)),
      ),
    ),
  );
  await state.init();
}
