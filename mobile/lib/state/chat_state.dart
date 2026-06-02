import 'package:agora_chat_sdk/agora_chat_sdk.dart' as ag;
import 'package:flutter/foundation.dart';

import '../agora/agora_chat_session.dart';
import '../api/client.dart';
import '../api/models.dart';

/// Holds chat history per conversation, sourced from Agora Chat SDK.
///
/// Backfill: history for a conversation is loaded once via the REST backend
/// (the Agora Chat callback persists every message there, so that path is
/// authoritative for "what happened before now").
///
/// Live updates: we register a single `ChatEventHandler` against
/// `ChatClient.chatManager`. Every inbound message routes by from/to into the
/// right session key (the sender for 1:1, the group id for groupchat).
///
/// Outbound: `sendToBot` and `sendToGroup` build a `ChatMessage` and send via
/// the SDK; the SDK echoes it back via the same listener so we don't need to
/// optimistically append.
class ChatState extends ChangeNotifier {
  final ApiClient _api;
  final AgoraChatSession _session;
  static const _handlerId = 'companion-chat-state';

  final Map<String, List<Message>> _bySessionKey = {};
  final Set<String> _loading = {};
  bool _listenerAttached = false;

  ChatState(this._api, this._session);

  @override
  void dispose() {
    _detachListener();
    super.dispose();
  }

  List<Message> messagesFor(String sessionKey) =>
      List.unmodifiable(_bySessionKey[sessionKey] ?? const []);

  bool isLoading(String sessionKey) => _loading.contains(sessionKey);

  /// Wire the SDK listener. Safe to call multiple times; idempotent.
  /// Called by the router after [AgoraChatSession.signIn] completes.
  void attachListener() {
    if (_listenerAttached) return;
    _session.chatManager.addEventHandler(
      _handlerId,
      ag.ChatEventHandler(onMessagesReceived: _onMessagesReceived),
    );
    _listenerAttached = true;
  }

  void _detachListener() {
    if (!_listenerAttached) return;
    try {
      _session.chatManager.removeEventHandler(_handlerId);
    } catch (_) {}
    _listenerAttached = false;
  }

  Future<void> loadBot(String userId) => _loadInto(
        sessionKey: userId,
        loader: () => _api.listUserMessages(userId),
      );

  Future<void> loadGroup(String groupId) => _loadInto(
        sessionKey: groupId,
        loader: () => _api.listGroupMessages(groupId),
      );

  Future<void> _loadInto({
    required String sessionKey,
    required Future<List<Message>> Function() loader,
  }) async {
    _loading.add(sessionKey);
    notifyListeners();
    try {
      final list = await loader();
      _bySessionKey[sessionKey] = list;
    } finally {
      _loading.remove(sessionKey);
      notifyListeners();
    }
  }

  /// Send a message to the AI bot.
  ///
  /// Bot conversations don't go through Agora Chat — the backend route
  /// `POST /api/users/<id>/chat` runs the message through ChatbotEngine
  /// (Gemini under the current config) and returns the inbound + outbound
  /// pair in one round-trip. We append both to local state so the screen
  /// updates immediately without waiting for any SDK listener.
  Future<void> sendToBot(String userId, String text) async {
    final pair = await _api.sendChatMessage(userId, text);
    final list = _bySessionKey.putIfAbsent(userId, () => []);
    list.addAll(pair);
    notifyListeners();
  }

  Future<void> sendToGroup({required String groupId, required String text}) async {
    final msg = ag.ChatMessage.createTxtSendMessage(
      targetId: groupId,
      content: text,
      chatType: ag.ChatType.GroupChat,
    );
    final sent = await _session.chatManager.sendMessage(msg);
    _appendFromAgora(sent, viewerUserId: _session.currentUserId);
  }

  void _onMessagesReceived(List<ag.ChatMessage> messages) {
    for (final msg in messages) {
      _appendFromAgora(msg, viewerUserId: _session.currentUserId);
    }
  }

  void _appendFromAgora(ag.ChatMessage msg, {String? viewerUserId}) {
    final mapped = _agoraToApp(msg, viewerUserId: viewerUserId);
    if (mapped == null) return;
    final list = _bySessionKey.putIfAbsent(mapped.sessionKey, () => []);
    list.add(mapped);
    notifyListeners();
  }

  Message? _agoraToApp(ag.ChatMessage msg, {String? viewerUserId}) {
    final body = msg.body;
    if (body is! ag.ChatTextMessageBody) return null;
    final isGroup = msg.chatType == ag.ChatType.GroupChat;
    final sessionKey = isGroup
        ? (msg.conversationId ?? msg.to ?? '')
        : (msg.from == viewerUserId
            ? (msg.to ?? '')
            : (msg.from ?? ''));
    if (sessionKey.isEmpty) return null;

    final from = msg.from ?? '';
    final isOutgoing = from == viewerUserId;
    return Message(
      sessionKey: sessionKey,
      userId: from,
      direction: isOutgoing ? MessageDirection.outgoing : MessageDirection.incoming,
      text: body.content,
      senderId: from,
      senderName: from == 'bot' ? 'Bot' : from,
      createdAt: DateTime.fromMillisecondsSinceEpoch(msg.serverTime),
    );
  }
}
