import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/models.dart';

class AppConfigState extends ChangeNotifier {
  final ApiClient _api;
  AppConfig _config = const AppConfig();
  bool _loaded = false;

  AppConfigState(this._api);

  AppConfig get config => _config;
  bool get isLoaded => _loaded;

  Future<void> load() async {
    try {
      _config = await _api.getConfig();
    } catch (_) {
      // Non-fatal — the app still works with default empty config.
    } finally {
      _loaded = true;
      notifyListeners();
    }
  }
}
