import 'dart:async';
// `unawaited` is in dart:async since 2.15.

import 'package:agora_rtc_engine/agora_rtc_engine.dart';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:provider/provider.dart';

import '../agora/agora_session.dart';
import '../api/client.dart';
import '../api/models.dart';

/// Group voice/video call screen, joined by all members who tap "Start call".
///
/// Channel name = group_id (so every member of the same group lands in the
/// same Agora channel). Local + remote video tiles, mute/camera toggle,
/// leave button. Tokens are fetched from the backend each join — App
/// Certificate stays server-side.
class GroupCallScreen extends StatefulWidget {
  final Group group;
  const GroupCallScreen({super.key, required this.group});

  @override
  State<GroupCallScreen> createState() => _GroupCallScreenState();
}

class _GroupCallScreenState extends State<GroupCallScreen> {
  RtcEngine? _engine;
  AgoraRtcToken? _token;
  final Set<int> _remoteUids = {};
  bool _muted = false;
  bool _cameraOff = false;
  bool _initializing = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _start());
  }

  @override
  void dispose() {
    _engine?.leaveChannel();
    // Don't release: AgoraSession owns lifecycle.
    super.dispose();
  }

  Future<void> _start() async {
    // Grab providers synchronously before any awaits — avoids the
    // "BuildContext across async gaps" warning.
    final session = context.read<AgoraSession>();
    final api = context.read<ApiClient>();

    // Ring the other group members. Best-effort: a failure here just means
    // they won't see a banner, the local call still proceeds normally.
    unawaited(_pingGroupMembers(api));

    // 1. Request mic + camera permissions.
    final perms = await [Permission.microphone, Permission.camera].request();
    if (perms[Permission.microphone] != PermissionStatus.granted ||
        perms[Permission.camera] != PermissionStatus.granted) {
      if (!mounted) return;
      setState(() {
        _initializing = false;
        _error = 'Mic and camera permissions are required for calls.';
      });
      return;
    }

    // 2. Fetch token from backend.
    AgoraRtcToken token;
    try {
      token = await session.ensureRtcToken(channel: widget.group.groupId);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _initializing = false;
        _error = 'Could not get call token.\n$e';
      });
      return;
    }
    _token = token;

    // 3. Init engine + handlers + join.
    final engine = await session.ensureRtcEngine(appId: token.appId);
    _engine = engine;
    engine.registerEventHandler(RtcEngineEventHandler(
      onUserJoined: (conn, uid, elapsed) {
        if (!mounted) return;
        setState(() => _remoteUids.add(uid));
      },
      onUserOffline: (conn, uid, reason) {
        if (!mounted) return;
        setState(() => _remoteUids.remove(uid));
      },
      onError: (err, msg) {
        if (!mounted) return;
        setState(() => _error = 'Agora error $err: $msg');
      },
    ));

    await engine.startPreview();
    await engine.joinChannel(
      token: token.token,
      channelId: token.channel,
      uid: token.uid,
      options: const ChannelMediaOptions(
        clientRoleType: ClientRoleType.clientRoleBroadcaster,
        channelProfile: ChannelProfileType.channelProfileCommunication,
      ),
    );
    if (mounted) setState(() => _initializing = false);
  }

  Future<void> _pingGroupMembers(ApiClient api) async {
    try {
      await api.notifyCallStart(widget.group.groupId);
    } catch (_) {
      // Best-effort. Worst case: members don't get the banner; they can still
      // join by opening the group manually.
    }
  }

  Future<void> _leave() async {
    await _engine?.leaveChannel();
    if (mounted) Navigator.of(context).pop();
  }

  Future<void> _toggleMute() async {
    final next = !_muted;
    await _engine?.muteLocalAudioStream(next);
    if (mounted) setState(() => _muted = next);
  }

  Future<void> _toggleCamera() async {
    final next = !_cameraOff;
    await _engine?.muteLocalVideoStream(next);
    if (mounted) setState(() => _cameraOff = next);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        title: Text(widget.group.name),
      ),
      body: SafeArea(child: _body(theme)),
    );
  }

  Widget _body(ThemeData theme) {
    if (_initializing) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(color: Colors.white),
            SizedBox(height: 12),
            Text('Connecting...', style: TextStyle(color: Colors.white70)),
          ],
        ),
      );
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: Colors.white, size: 48),
              const SizedBox(height: 8),
              Text(_error!,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white)),
              const SizedBox(height: 16),
              FilledButton.tonal(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Close'),
              ),
            ],
          ),
        ),
      );
    }

    return Column(
      children: [
        Expanded(child: _videoGrid()),
        _controlBar(theme),
      ],
    );
  }

  Widget _videoGrid() {
    final tiles = <Widget>[
      _localTile(),
      for (final uid in _remoteUids) _remoteTile(uid),
    ];
    final count = tiles.length;
    final cross = count <= 1 ? 1 : (count <= 4 ? 2 : 3);
    return Padding(
      padding: const EdgeInsets.all(8),
      child: GridView.count(
        crossAxisCount: cross,
        crossAxisSpacing: 8,
        mainAxisSpacing: 8,
        childAspectRatio: 3 / 4,
        children: tiles,
      ),
    );
  }

  Widget _localTile() {
    final engine = _engine;
    if (engine == null) {
      return _placeholderTile('You', muted: _muted, cameraOff: _cameraOff);
    }
    return _videoFrame(
      label: 'You',
      muted: _muted,
      cameraOff: _cameraOff,
      child: _cameraOff
          ? _avatarPlaceholder()
          : AgoraVideoView(
              controller: VideoViewController(
                rtcEngine: engine,
                canvas: const VideoCanvas(uid: 0),
              ),
            ),
    );
  }

  Widget _remoteTile(int uid) {
    final engine = _engine;
    final token = _token;
    if (engine == null || token == null) return _placeholderTile('$uid');
    return _videoFrame(
      label: 'User $uid',
      child: AgoraVideoView(
        controller: VideoViewController.remote(
          rtcEngine: engine,
          canvas: VideoCanvas(uid: uid),
          connection: RtcConnection(channelId: token.channel),
        ),
      ),
    );
  }

  Widget _videoFrame({
    required String label,
    bool muted = false,
    bool cameraOff = false,
    required Widget child,
  }) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Stack(
        children: [
          Positioned.fill(child: child),
          Positioned(
            left: 8,
            bottom: 8,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.6),
                borderRadius: BorderRadius.circular(999),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(label,
                      style: const TextStyle(color: Colors.white, fontSize: 12)),
                  if (muted) ...[
                    const SizedBox(width: 6),
                    const Icon(Icons.mic_off,
                        color: Colors.redAccent, size: 14),
                  ],
                  if (cameraOff) ...[
                    const SizedBox(width: 6),
                    const Icon(Icons.videocam_off,
                        color: Colors.redAccent, size: 14),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _avatarPlaceholder() => Container(
        color: const Color(0xFF1B1E22),
        alignment: Alignment.center,
        child: const Icon(Icons.person, color: Colors.white70, size: 48),
      );

  Widget _placeholderTile(String label, {bool muted = false, bool cameraOff = false}) =>
      _videoFrame(
        label: label,
        muted: muted,
        cameraOff: cameraOff,
        child: _avatarPlaceholder(),
      );

  Widget _controlBar(ThemeData theme) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _circleAction(
              icon: _muted ? Icons.mic_off : Icons.mic,
              color: _muted ? Colors.redAccent : Colors.white,
              onTap: _toggleMute,
            ),
            _circleAction(
              icon: Icons.call_end,
              color: Colors.white,
              background: Colors.redAccent,
              onTap: _leave,
              large: true,
            ),
            _circleAction(
              icon: _cameraOff ? Icons.videocam_off : Icons.videocam,
              color: _cameraOff ? Colors.redAccent : Colors.white,
              onTap: _toggleCamera,
            ),
          ],
        ),
      ),
    );
  }

  Widget _circleAction({
    required IconData icon,
    required Color color,
    Color background = const Color(0x55FFFFFF),
    required VoidCallback onTap,
    bool large = false,
  }) {
    final size = large ? 72.0 : 56.0;
    return InkResponse(
      onTap: onTap,
      radius: size,
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: background,
          shape: BoxShape.circle,
        ),
        child: Icon(icon, color: color, size: large ? 32 : 26),
      ),
    );
  }
}
