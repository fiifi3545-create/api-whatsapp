import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import '../api/client.dart';

/// Coordinates Firebase Messaging and backend device registration.
///
/// **Setup required to actually receive pushes:**
/// 1. Run `flutterfire configure` (CLI) to generate `lib/firebase_options.dart`
///    and drop `android/app/google-services.json` + `ios/Runner/GoogleService-Info.plist`.
/// 2. Update [init] to pass `DefaultFirebaseOptions.currentPlatform` to
///    `Firebase.initializeApp(...)`.
/// 3. Make sure the backend has FCM_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS set.
///
/// Until then, [init] catches the missing-config error and degrades to a no-op.
class NotificationsService {
  final ApiClient _api;
  String? _registeredToken;
  bool _initialized = false;
  Stream<RemoteMessage>? _onForeground;

  NotificationsService(this._api);

  bool get isReady => _initialized;
  Stream<RemoteMessage>? get onForegroundMessage => _onForeground;

  Future<void> init({required String userId}) async {
    if (_initialized) return;
    try {
      await Firebase.initializeApp();
    } catch (e) {
      debugPrint('NotificationsService: Firebase not configured, push disabled ($e)');
      return;
    }

    final messaging = FirebaseMessaging.instance;
    try {
      await messaging.requestPermission(alert: true, badge: true, sound: true);
      final token = await messaging.getToken();
      if (token != null && token.isNotEmpty && token != _registeredToken) {
        await _register(userId: userId, token: token, messaging: messaging);
      }
      messaging.onTokenRefresh.listen((newToken) {
        _register(userId: userId, token: newToken, messaging: messaging);
      });
      _onForeground = FirebaseMessaging.onMessage;
      _initialized = true;
    } catch (e) {
      debugPrint('NotificationsService: FCM init failed ($e)');
    }
  }

  Future<void> _register({
    required String userId,
    required String token,
    required FirebaseMessaging messaging,
  }) async {
    final platform = defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';
    try {
      // ApiClient doesn't yet have device endpoints — call them ad-hoc.
      await _postDevice(userId: userId, token: token, platform: platform);
      _registeredToken = token;
    } catch (e) {
      debugPrint('NotificationsService: register failed ($e)');
    }
  }

  Future<void> _postDevice({
    required String userId,
    required String token,
    required String platform,
  }) async {
    await _api.registerDevice(userId: userId, fcmToken: token, platform: platform);
  }

  Future<void> deregister({required String userId}) async {
    final t = _registeredToken;
    _registeredToken = null;
    if (t == null) return;
    try {
      await _api.unregisterDevice(userId: userId, fcmToken: t);
    } catch (_) {
      // best effort
    }
  }
}
