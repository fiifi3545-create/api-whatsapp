import 'dart:async';

import 'package:agora_rtm/agora_rtm.dart';
import 'package:flutter/foundation.dart';

import '../agora/rtm_session.dart';

/// Tracks who's currently online in each RTM-subscribed group.
///
/// Subscribes once to [RtmSession.presenceEvents] and folds the events into a
/// per-group set of online user IDs. Widgets read via [onlineMembers] or
/// [isOnline] and rebuild via `context.watch<PresenceState>()`.
///
/// We bind to whichever group_id corresponds to the channel name on the event
/// (channel names are `g_<groupId>` — see [RtmSession.channelForGroup]). If a
/// channel name doesn't follow that pattern, the event is ignored.
class PresenceState extends ChangeNotifier {
  StreamSubscription<PresenceEvent>? _sub;
  final Map<String, Set<String>> _onlineByGroup = {};

  PresenceState(RtmSession session) {
    _sub = session.presenceEvents.listen(_onEvent);
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  Set<String> onlineMembers(String groupId) =>
      Set.unmodifiable(_onlineByGroup[groupId] ?? const {});

  bool isOnline(String groupId, String userId) =>
      _onlineByGroup[groupId]?.contains(userId) ?? false;

  int onlineCount(String groupId) => _onlineByGroup[groupId]?.length ?? 0;

  /// Visible for testing. Production code uses the listener wired in the ctor.
  @visibleForTesting
  void handleEvent(PresenceEvent event) => _onEvent(event);

  void _onEvent(PresenceEvent event) {
    final channel = event.channelName;
    if (channel == null) return;
    final groupId = _groupIdFromChannel(channel);
    if (groupId == null) return;

    final set = _onlineByGroup.putIfAbsent(groupId, () => <String>{});
    var changed = false;

    switch (event.type) {
      case RtmPresenceEventType.snapshot:
        // Replace the set with the snapshot from the SDK.
        final snapshotUsers = event.snapshot?.userStateList
                ?.map((u) => u.userId)
                .whereType<String>()
                .toSet() ??
            <String>{};
        if (!_setEqual(set, snapshotUsers)) {
          set
            ..clear()
            ..addAll(snapshotUsers);
          changed = true;
        }
      case RtmPresenceEventType.interval:
        // Periodic delta: join/leave/timeout lists since last interval.
        final joins = event.interval?.joinUserList?.users ?? const [];
        final leaves = event.interval?.leaveUserList?.users ?? const [];
        final timeouts = event.interval?.timeoutUserList?.users ?? const [];
        for (final u in joins) {
          if (set.add(u)) changed = true;
        }
        for (final u in leaves) {
          if (set.remove(u)) changed = true;
        }
        for (final u in timeouts) {
          if (set.remove(u)) changed = true;
        }
      case RtmPresenceEventType.remoteJoinChannel:
        final user = event.publisher;
        if (user != null && set.add(user)) changed = true;
      case RtmPresenceEventType.remoteLeaveChannel:
      case RtmPresenceEventType.remoteTimeout:
        final user = event.publisher;
        if (user != null && set.remove(user)) changed = true;
      case RtmPresenceEventType.remoteStateChanged:
      case RtmPresenceEventType.errorOutOfService:
      case RtmPresenceEventType.none:
      case null:
        // No membership change; ignore.
        break;
    }

    if (changed) notifyListeners();
  }

  static String? _groupIdFromChannel(String channelName) {
    const prefix = 'g_';
    if (!channelName.startsWith(prefix)) return null;
    final id = channelName.substring(prefix.length);
    return id.isEmpty ? null : id;
  }

  static bool _setEqual(Set<String> a, Set<String> b) =>
      a.length == b.length && a.containsAll(b);
}
