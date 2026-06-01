import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Holds the authenticated identity.
///
/// JWT lives in secure storage; user_id and display name are convenience
/// caches in SharedPreferences so the home screen can render before any
/// network call. The JWT is the source of truth for who the user is.
class Session extends ChangeNotifier {
  static const _kUserIdKey = 'session.user_id';
  static const _kDisplayNameKey = 'session.display_name';
  static const _kTokenKey = 'session.jwt';

  final FlutterSecureStorage _secure;
  Session({FlutterSecureStorage? secureStorage})
      : _secure = secureStorage ?? const FlutterSecureStorage();

  String? _userId;
  String _displayName = '';
  String? _token;
  bool _ready = false;

  String? get userId => _userId;
  String get displayName => _displayName;
  String? get token => _token;
  bool get isReady => _ready;
  bool get isAuthenticated => _token != null && _token!.isNotEmpty;

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _userId = prefs.getString(_kUserIdKey);
    _displayName = prefs.getString(_kDisplayNameKey) ?? '';
    _token = await _secure.read(key: _kTokenKey);
    _ready = true;
    notifyListeners();
  }

  Future<void> setAuthenticated({
    required String userId,
    required String token,
    String displayName = '',
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUserIdKey, userId);
    await prefs.setString(_kDisplayNameKey, displayName);
    await _secure.write(key: _kTokenKey, value: token);
    _userId = userId;
    _displayName = displayName;
    _token = token;
    notifyListeners();
  }

  Future<void> updateDisplayName(String name) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kDisplayNameKey, name);
    _displayName = name;
    notifyListeners();
  }

  Future<void> signOut() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kUserIdKey);
    await prefs.remove(_kDisplayNameKey);
    await _secure.delete(key: _kTokenKey);
    _userId = null;
    _displayName = '';
    _token = null;
    notifyListeners();
  }
}
