import 'dart:async';

import 'package:flutter/foundation.dart';

/// Snapshot of an inbound call invitation, populated from an FCM data message.
@immutable
class IncomingCall {
  final String groupId;
  final String groupName;
  final String initiatorId;
  final String initiatorName;
  final DateTime receivedAt;

  const IncomingCall({
    required this.groupId,
    required this.groupName,
    required this.initiatorId,
    required this.initiatorName,
    required this.receivedAt,
  });

  factory IncomingCall.fromFcmData(Map<String, dynamic> data) => IncomingCall(
        groupId: (data['group_id'] as String?) ?? '',
        groupName: (data['group_name'] as String?) ?? '',
        initiatorId: (data['initiator_id'] as String?) ?? '',
        initiatorName: (data['initiator_name'] as String?) ?? '',
        receivedAt: DateTime.now(),
      );

  bool get isValid => groupId.isNotEmpty && initiatorId.isNotEmpty;
}

/// Holds the currently pending incoming-call invitation (if any).
///
/// Fed from two sources:
///   - Foreground FCM messages with `data.type == "call_invitation"`
///   - Background-tap handlers that hand off the same payload via [announce]
///
/// The UI watches this and renders a banner / overlay; tapping accept routes
/// to the group call screen and clears the pending call.
class IncomingCallState extends ChangeNotifier {
  static const Duration _autoDismiss = Duration(seconds: 45);

  IncomingCall? _pending;
  Timer? _autoDismissTimer;

  IncomingCall? get pending => _pending;
  bool get hasPending => _pending != null;

  /// Replace any pending call with a new one and start the auto-dismiss timer.
  /// If the same call arrives twice (FCM retry, RTM bridge, etc.) we keep
  /// the original [receivedAt] so the timer doesn't reset.
  void announce(IncomingCall call) {
    if (!call.isValid) return;
    final current = _pending;
    if (current != null &&
        current.groupId == call.groupId &&
        current.initiatorId == call.initiatorId) {
      return;
    }
    _pending = call;
    _autoDismissTimer?.cancel();
    _autoDismissTimer = Timer(_autoDismiss, () {
      if (_pending == call) dismiss();
    });
    notifyListeners();
  }

  void dismiss() {
    if (_pending == null) return;
    _pending = null;
    _autoDismissTimer?.cancel();
    _autoDismissTimer = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _autoDismissTimer?.cancel();
    super.dispose();
  }
}
