import 'dart:async';

import 'package:agora_rtm/agora_rtm.dart';

import 'agora_session.dart';

/// Owns the Agora RTM (Real-Time Messaging) client lifecycle.
///
/// On [signIn] we create an `RtmClient`, log in with the RTM token from the
/// backend, and wire a presence listener that broadcasts every event over
/// [presenceEvents] for `PresenceState` to consume.
///
/// Each group we care about is mapped to an RTM channel named `g_<groupId>`.
/// Subscribing with `withPresence: true` makes Agora deliver a `snapshot`
/// event listing current online members, plus `remoteJoin/Leave/Timeout`
/// events going forward.
class RtmSession {
  final AgoraSession _agora;

  RtmSession(this._agora);

  RtmClient? _client;
  String? _userId;
  final StreamController<PresenceEvent> _presence =
      StreamController<PresenceEvent>.broadcast();

  /// Live stream of presence events received from any subscribed channel.
  Stream<PresenceEvent> get presenceEvents => _presence.stream;
  String? get currentUserId => _userId;
  bool get isSignedIn => _client != null;

  /// Map a backend group_id to its RTM channel name. Channel names are
  /// global across all clients — every member of a given group must use
  /// the same name to land in the same presence room.
  static String channelForGroup(String groupId) => 'g_$groupId';

  /// Initialise the RTM client + log in. Idempotent on the same userId.
  Future<void> signIn(String userId) async {
    if (_client != null && _userId == userId) return;
    if (_client != null) {
      await signOut();
    }

    final token = await _agora.ensureRtmToken();
    final (initStatus, client) = await RTM(token.appId, userId);
    if (initStatus.error) {
      throw StateError(
        'RTM init failed (${initStatus.errorCode}): ${initStatus.reason}',
      );
    }

    client.addListener(presence: _presence.add);

    final (loginStatus, _) = await client.login(token.token);
    if (loginStatus.error) {
      // Best-effort cleanup before surfacing the failure.
      try { await client.release(); } catch (_) {}
      throw StateError(
        'RTM login failed (${loginStatus.errorCode}): ${loginStatus.reason}',
      );
    }

    _client = client;
    _userId = userId;
  }

  Future<void> signOut() async {
    final client = _client;
    _client = null;
    _userId = null;
    if (client == null) return;
    try { await client.logout(); } catch (_) {}
    try { await client.release(); } catch (_) {}
  }

  Future<void> subscribeToGroup(String groupId) async {
    final client = _client;
    if (client == null) return;
    await client.subscribe(
      channelForGroup(groupId),
      withMessage: false,    // chat goes through Agora Chat, not RTM
      withPresence: true,
    );
  }

  Future<void> unsubscribeFromGroup(String groupId) async {
    final client = _client;
    if (client == null) return;
    try {
      await client.unsubscribe(channelForGroup(groupId));
    } catch (_) {
      // Ignore — could be already-unsubscribed if the connection bounced.
    }
  }
}
