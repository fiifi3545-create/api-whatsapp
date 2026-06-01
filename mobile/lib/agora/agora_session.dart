import 'dart:async';

import 'package:agora_rtc_engine/agora_rtc_engine.dart';

import '../api/client.dart';
import '../api/models.dart';

/// Lazy-init wrapper around Agora SDKs.
///
/// - RTC: `RtcEngine` is created on first `joinChannel` and re-used.
/// - Chat / RTM: tokens are fetched lazily; SDK init is deferred to whichever
///   feature actually needs them (next iteration — only RTC is wired this
///   round, so chat/rtm tokens are exposed but the SDKs aren't initialized).
///
/// One instance per app lifetime — stash via Provider.
class AgoraSession {
  final ApiClient _api;

  AgoraSession(this._api);

  RtcEngine? _rtcEngine;
  AgoraRtcToken? _lastRtcToken;
  AgoraRtmToken? _lastRtmToken;
  AgoraChatToken? _lastChatToken;

  RtcEngine? get rtcEngine => _rtcEngine;
  AgoraRtcToken? get lastRtcToken => _lastRtcToken;
  AgoraRtmToken? get lastRtmToken => _lastRtmToken;
  AgoraChatToken? get lastChatToken => _lastChatToken;

  /// Get a current RTC token for [channel]. Refreshes if cached one is for a
  /// different channel or within 60s of expiry.
  Future<AgoraRtcToken> ensureRtcToken({
    required String channel,
    int uid = 0,
  }) async {
    final cached = _lastRtcToken;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    if (cached != null &&
        cached.channel == channel &&
        cached.uid == uid &&
        cached.expiresAt - now > 60) {
      return cached;
    }
    final token = await _api.fetchRtcToken(channel: channel, uid: uid);
    _lastRtcToken = token;
    return token;
  }

  Future<AgoraRtmToken> ensureRtmToken() async {
    final cached = _lastRtmToken;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    if (cached != null && cached.expiresAt - now > 60) return cached;
    final token = await _api.fetchRtmToken();
    _lastRtmToken = token;
    return token;
  }

  Future<AgoraChatToken> ensureChatToken() async {
    final cached = _lastChatToken;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    if (cached != null && cached.expiresAt - now > 60) return cached;
    final token = await _api.fetchChatToken();
    _lastChatToken = token;
    return token;
  }

  /// Initialise and return the RTC engine. Idempotent. Caller is responsible
  /// for adding event handlers via [RtcEngine.registerEventHandler] before
  /// joining a channel.
  Future<RtcEngine> ensureRtcEngine({required String appId}) async {
    if (_rtcEngine != null) return _rtcEngine!;
    final engine = createAgoraRtcEngine();
    await engine.initialize(RtcEngineContext(
      appId: appId,
      channelProfile: ChannelProfileType.channelProfileCommunication,
    ));
    await engine.enableVideo();
    await engine.enableAudio();
    _rtcEngine = engine;
    return engine;
  }

  /// Tear down everything. Call on sign-out.
  Future<void> dispose() async {
    final engine = _rtcEngine;
    _rtcEngine = null;
    _lastRtcToken = null;
    _lastRtmToken = null;
    _lastChatToken = null;
    if (engine != null) {
      try {
        await engine.leaveChannel();
      } catch (_) {}
      try {
        await engine.release();
      } catch (_) {}
    }
  }
}
