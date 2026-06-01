import 'package:flutter_test/flutter_test.dart';

import 'package:companion/state/incoming_call_state.dart';

IncomingCall _call({
  String groupId = 'g1',
  String groupName = 'CS401',
  String initiatorId = 'alice',
  String initiatorName = 'Alice',
}) => IncomingCall(
      groupId: groupId,
      groupName: groupName,
      initiatorId: initiatorId,
      initiatorName: initiatorName,
      receivedAt: DateTime.now(),
    );

void main() {
  test('starts with no pending call', () {
    final s = IncomingCallState();
    expect(s.pending, isNull);
    expect(s.hasPending, isFalse);
  });

  test('announce sets pending + notifies listeners', () {
    final s = IncomingCallState();
    var notifications = 0;
    s.addListener(() => notifications++);
    s.announce(_call());
    expect(s.hasPending, isTrue);
    expect(s.pending!.initiatorId, 'alice');
    expect(notifications, 1);
  });

  test('announce ignores invalid payloads (missing group_id)', () {
    final s = IncomingCallState();
    s.announce(_call(groupId: ''));
    expect(s.hasPending, isFalse);
  });

  test('announce ignores invalid payloads (missing initiator_id)', () {
    final s = IncomingCallState();
    s.announce(_call(initiatorId: ''));
    expect(s.hasPending, isFalse);
  });

  test('dismiss clears pending + notifies', () {
    final s = IncomingCallState();
    s.announce(_call());
    var notifications = 0;
    s.addListener(() => notifications++);
    s.dismiss();
    expect(s.hasPending, isFalse);
    expect(notifications, 1);
  });

  test('dismiss is a no-op when nothing is pending', () {
    final s = IncomingCallState();
    var notifications = 0;
    s.addListener(() => notifications++);
    s.dismiss();
    expect(notifications, 0);
  });

  test('duplicate announce for the same call is a no-op', () {
    final s = IncomingCallState();
    s.announce(_call());
    var notifications = 0;
    s.addListener(() => notifications++);
    s.announce(_call());  // same initiator + same group
    expect(notifications, 0);
  });

  test('different initiator overwrites the pending call', () {
    final s = IncomingCallState();
    s.announce(_call(initiatorId: 'alice'));
    var notifications = 0;
    s.addListener(() => notifications++);
    s.announce(_call(initiatorId: 'bob'));
    expect(s.pending!.initiatorId, 'bob');
    expect(notifications, 1);
  });

  test('IncomingCall.fromFcmData parses a backend payload', () {
    final call = IncomingCall.fromFcmData({
      'type': 'call_invitation',
      'group_id': 'g1',
      'group_name': 'CS401',
      'initiator_id': 'alice',
      'initiator_name': 'Alice',
    });
    expect(call.groupId, 'g1');
    expect(call.groupName, 'CS401');
    expect(call.initiatorId, 'alice');
    expect(call.initiatorName, 'Alice');
    expect(call.isValid, isTrue);
  });

  test('IncomingCall.fromFcmData with missing fields is invalid', () {
    final call = IncomingCall.fromFcmData({'type': 'call_invitation'});
    expect(call.isValid, isFalse);
  });
}
