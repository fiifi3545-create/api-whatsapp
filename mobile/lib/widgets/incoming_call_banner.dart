import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';
import '../screens/group_call_screen.dart';
import '../state/incoming_call_state.dart';

/// Top-of-screen banner that appears when [IncomingCallState] has a pending
/// invitation. Shows caller + group name with Accept / Decline actions.
///
/// Wraps its [child] in a `Column` so the banner pushes the rest of the UI
/// down rather than overlaying it — simpler than an OverlayEntry and lets
/// the user keep using the underlying screen if they tap Decline.
class IncomingCallBanner extends StatelessWidget {
  final Widget child;
  const IncomingCallBanner({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    final call = context.watch<IncomingCallState>().pending;
    return Column(
      children: [
        if (call != null) _Banner(call: call),
        Expanded(child: child),
      ],
    );
  }
}

class _Banner extends StatelessWidget {
  final IncomingCall call;
  const _Banner({required this.call});

  String get _displayName =>
      call.initiatorName.isNotEmpty ? call.initiatorName : call.initiatorId;

  String get _displayGroup =>
      call.groupName.isNotEmpty ? call.groupName : 'a study group';

  Future<void> _accept(BuildContext context) async {
    final api = context.read<ApiClient>();
    final state = context.read<IncomingCallState>();
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);

    // Resolve the group from the backend so GroupCallScreen has the full
    // model (members list, join code, etc). If the fetch fails we still
    // open the call with a minimal stub — the call screen only needs the
    // group_id for the channel name and the name for the title bar.
    Group? group;
    try {
      group = await api.getGroup(call.groupId);
    } catch (_) {
      group = null;
    }
    state.dismiss();
    if (group == null) {
      group = Group(
        groupId: call.groupId,
        name: _displayGroup,
        creatorId: call.initiatorId,
        joinCode: '',
        members: const [],
      );
      messenger.showSnackBar(const SnackBar(
        content: Text('Joining call (group details unavailable)…'),
      ));
    }
    await navigator.push(MaterialPageRoute(
      builder: (_) => GroupCallScreen(group: group!),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.primaryContainer,
      elevation: 2,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 12, 12),
          child: Row(
            children: [
              CircleAvatar(
                backgroundColor: scheme.primary,
                foregroundColor: scheme.onPrimary,
                child: const Icon(Icons.videocam),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$_displayName is calling',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: scheme.onPrimaryContainer,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      _displayGroup,
                      style: TextStyle(
                        fontSize: 12,
                        color: scheme.onPrimaryContainer.withValues(alpha: 0.8),
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Decline',
                onPressed: () => context.read<IncomingCallState>().dismiss(),
                icon: const Icon(Icons.call_end),
                color: scheme.error,
              ),
              FilledButton.icon(
                onPressed: () => _accept(context),
                icon: const Icon(Icons.call),
                label: const Text('Join'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
