import 'package:flutter/foundation.dart';

import '../api/client.dart';
import '../api/models.dart';

class GroupsState extends ChangeNotifier {
  final ApiClient _api;
  GroupsState(this._api);

  List<Group> _groups = const [];
  bool _loading = false;
  Object? _error;

  List<Group> get groups => _groups;
  bool get isLoading => _loading;
  Object? get error => _error;

  Future<void> refresh(String userId) async {
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      _groups = await _api.listUserGroups(userId);
    } catch (e) {
      _error = e;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<Group?> createGroup({required String name, required String creatorId}) async {
    try {
      final g = await _api.createGroup(name: name, creatorId: creatorId);
      _groups = [..._groups, g];
      notifyListeners();
      return g;
    } catch (e) {
      _error = e;
      notifyListeners();
      return null;
    }
  }

  Future<Group?> joinGroup({required String code, required String userId}) async {
    try {
      final g = await _api.joinGroup(code: code, userId: userId);
      if (g != null && !_groups.any((existing) => existing.groupId == g.groupId)) {
        _groups = [..._groups, g];
        notifyListeners();
      }
      return g;
    } catch (e) {
      _error = e;
      notifyListeners();
      return null;
    }
  }

  Future<bool> deleteGroup({required String groupId, required String requesterId}) async {
    final ok = await _api.deleteGroup(groupId: groupId, requesterId: requesterId);
    if (ok) {
      _groups = _groups.where((g) => g.groupId != groupId).toList();
      notifyListeners();
    }
    return ok;
  }
}
