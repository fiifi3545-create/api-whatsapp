import 'dart:async';

import 'package:agora_rtm/agora_rtm.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:companion/agora/rtm_session.dart';
import 'package:companion/state/presence_state.dart';

/// We feed PresenceEvent directly via handleEvent instead of standing up a
/// real RtmClient. The single dependency we still need is something that
/// exposes a `presenceEvents` stream so the ctor compiles — a stub does it.
class _StubRtmSession implements RtmSession {
  final _controller = StreamController<PresenceEvent>.broadcast();
  @override
  Stream<PresenceEvent> get presenceEvents => _controller.stream;
  @override
  String? get currentUserId => 'self';
  @override
  bool get isSignedIn => true;
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

PresenceEvent _snapshot(String channel, List<String> users) => PresenceEvent(
      type: RtmPresenceEventType.snapshot,
      channelName: channel,
      snapshot: SnapshotInfo(
        userStateList: [for (final u in users) UserState(userId: u)],
      ),
    );

PresenceEvent _join(String channel, String user) => PresenceEvent(
      type: RtmPresenceEventType.remoteJoinChannel,
      channelName: channel,
      publisher: user,
    );

PresenceEvent _leave(String channel, String user) => PresenceEvent(
      type: RtmPresenceEventType.remoteLeaveChannel,
      channelName: channel,
      publisher: user,
    );

PresenceEvent _timeout(String channel, String user) => PresenceEvent(
      type: RtmPresenceEventType.remoteTimeout,
      channelName: channel,
      publisher: user,
    );

PresenceEvent _interval(String channel, {
  List<String> joins = const [],
  List<String> leaves = const [],
  List<String> timeouts = const [],
}) =>
    PresenceEvent(
      type: RtmPresenceEventType.interval,
      channelName: channel,
      interval: IntervalInfo(
        joinUserList: UserList(users: joins),
        leaveUserList: UserList(users: leaves),
        timeoutUserList: UserList(users: timeouts),
      ),
    );

void main() {
  late PresenceState state;

  setUp(() {
    state = PresenceState(_StubRtmSession());
  });

  tearDown(() {
    state.dispose();
  });

  test('snapshot loads initial online set for a group', () {
    state.handleEvent(_snapshot('g_g1', ['alice', 'bob']));
    expect(state.onlineMembers('g1'), {'alice', 'bob'});
    expect(state.onlineCount('g1'), 2);
    expect(state.isOnline('g1', 'alice'), isTrue);
    expect(state.isOnline('g1', 'carol'), isFalse);
  });

  test('remoteJoinChannel adds a user', () {
    state.handleEvent(_snapshot('g_g1', ['alice']));
    state.handleEvent(_join('g_g1', 'bob'));
    expect(state.onlineMembers('g1'), {'alice', 'bob'});
  });

  test('remoteLeaveChannel removes a user', () {
    state.handleEvent(_snapshot('g_g1', ['alice', 'bob']));
    state.handleEvent(_leave('g_g1', 'alice'));
    expect(state.onlineMembers('g1'), {'bob'});
  });

  test('remoteTimeout removes a user', () {
    state.handleEvent(_snapshot('g_g1', ['alice', 'bob']));
    state.handleEvent(_timeout('g_g1', 'bob'));
    expect(state.onlineMembers('g1'), {'alice'});
  });

  test('interval applies joins/leaves/timeouts atomically', () {
    state.handleEvent(_snapshot('g_g1', ['alice', 'bob']));
    state.handleEvent(_interval(
      'g_g1',
      joins: ['carol'],
      leaves: ['alice'],
      timeouts: ['bob'],
    ));
    expect(state.onlineMembers('g1'), {'carol'});
  });

  test('events from a different group do not leak', () {
    state.handleEvent(_snapshot('g_g1', ['alice']));
    state.handleEvent(_snapshot('g_g2', ['bob']));
    expect(state.onlineMembers('g1'), {'alice'});
    expect(state.onlineMembers('g2'), {'bob'});
  });

  test('events on non-group channels are ignored', () {
    state.handleEvent(_snapshot('unrelated-channel', ['alice']));
    expect(state.onlineMembers('unrelated-channel'), isEmpty);
  });

  test('snapshot replaces (not merges) the prior online set', () {
    state.handleEvent(_snapshot('g_g1', ['alice', 'bob', 'carol']));
    state.handleEvent(_snapshot('g_g1', ['alice']));  // server-side reset
    expect(state.onlineMembers('g1'), {'alice'});
  });

  test('notifies listeners on real changes only', () async {
    var notifications = 0;
    state.addListener(() => notifications++);
    state.handleEvent(_snapshot('g_g1', ['alice']));
    expect(notifications, 1);
    // A second join of the same already-online user shouldn't notify.
    state.handleEvent(_join('g_g1', 'alice'));
    expect(notifications, 1);
    // A new user joining does notify.
    state.handleEvent(_join('g_g1', 'bob'));
    expect(notifications, 2);
  });
}
