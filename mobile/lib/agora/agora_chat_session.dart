import 'dart:async';

import 'package:agora_chat_sdk/agora_chat_sdk.dart';

import '../api/client.dart';

/// One-shot initialiser + login for the Agora Chat SDK.
///
/// The mobile app calls [signIn] once after authentication. We:
///   1. Fetch the user's chat token from our backend (`/api/agora/chat-token`)
///   2. Initialise `ChatClient` with the app key from that response
///   3. Log in with [ChatClient.loginWithToken]
///
/// On sign-out, [signOut] tears it all down. The Chat SDK is a global
/// singleton; this class just owns the lifecycle alongside our Provider tree.
class AgoraChatSession {
  final ApiClient _api;

  AgoraChatSession(this._api);

  bool _signedIn = false;
  String? _userId;

  bool get isSignedIn => _signedIn;
  String? get currentUserId => _userId;

  /// The Agora Chat ChatManager. Throws if [signIn] hasn't completed.
  ChatManager get chatManager => ChatClient.getInstance.chatManager;

  Future<void> signIn(String userId) async {
    if (_signedIn && _userId == userId) return;
    if (_signedIn && _userId != userId) {
      // Different user — log the previous one out first.
      await signOut();
    }

    final token = await _api.fetchChatToken();

    // ChatOptions.init is idempotent on the same appKey. If the appKey ever
    // changes (different Agora project) a release+init cycle is needed; we
    // don't expect that mid-session.
    try {
      await ChatClient.getInstance.init(ChatOptions(
        appKey: token.appKey,
        autoLogin: false,
      ));
    } catch (_) {
      // Already initialized.
    }

    await ChatClient.getInstance.loginWithToken(token.userId, token.token);
    _signedIn = true;
    _userId = token.userId;
  }

  Future<void> signOut() async {
    if (!_signedIn) return;
    try {
      await ChatClient.getInstance.logout(true);
    } catch (_) {}
    _signedIn = false;
    _userId = null;
  }
}
