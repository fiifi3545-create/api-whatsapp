import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/models.dart';
import '../state/chat_state.dart';
import '../state/session.dart';
import '../widgets/message_bubble.dart';

/// Live 1:1 chat with the bot over WebSocket.
///
/// Backfills history via REST on open, then appends realtime events as they
/// arrive. Send goes through `ChatState.sendToBot` → WS → backend → bot
/// reply → broadcast back to this socket. The bot's reply text is produced
/// by whichever NLP backend is configured server-side (Gemini, Dialogflow,
/// or Gemma).
class MessagesScreen extends StatefulWidget {
  const MessagesScreen({super.key});

  @override
  State<MessagesScreen> createState() => _MessagesScreenState();
}

class _MessagesScreenState extends State<MessagesScreen> {
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  String? _error;
  int _lastLen = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final userId = context.read<Session>().userId;
    if (userId == null) return;
    try {
      await context.read<ChatState>().loadBot(userId);
      _scrollToBottom();
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '$e');
    }
  }

  void _send() {
    final text = _input.text.trim();
    if (text.isEmpty) return;
    final userId = context.read<Session>().userId;
    if (userId == null) return;
    _input.clear();
    context.read<ChatState>().sendToBot(userId, text);
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final session = context.watch<Session>();
    final chat = context.watch<ChatState>();
    final userId = session.userId ?? '';
    final messages = chat.messagesFor(userId);
    final loading = chat.isLoading(userId);

    // Auto-scroll on new messages.
    if (messages.length != _lastLen) {
      _lastLen = messages.length;
      _scrollToBottom();
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Chat with the bot'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(16),
          child: Padding(
            padding: const EdgeInsets.only(bottom: 8, left: 16, right: 16),
            child: Text(
              'Live chat — replies stream from the bot in real-time.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        ),
      ),
      body: Column(
        children: [
          Expanded(child: _body(theme, loading, messages, userId)),
          _composer(theme),
        ],
      ),
    );
  }

  Widget _body(
    ThemeData theme,
    bool loading,
    List<Message> messages,
    String userId,
  ) {
    if (loading && messages.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null && messages.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_outlined, size: 48),
              const SizedBox(height: 8),
              Text('Could not load messages.\n$_error',
                  textAlign: TextAlign.center),
              const SizedBox(height: 12),
              FilledButton.tonalIcon(
                onPressed: () {
                  setState(() => _error = null);
                  _load();
                },
                icon: const Icon(Icons.refresh),
                label: const Text('Try again'),
              ),
            ],
          ),
        ),
      );
    }
    if (messages.isEmpty) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          Icon(Icons.chat_bubble_outline,
              size: 56, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(height: 12),
          const Center(
            child: Text('Say hi to get started.',
                style: TextStyle(fontWeight: FontWeight.w600)),
          ),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 40),
            child: Text(
              'Try: "library hours", "how do I register for courses", "transcript request".',
              textAlign: TextAlign.center,
              style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      );
    }
    return ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: messages.length,
      itemBuilder: (_, i) => MessageBubble(message: messages[i]),
    );
  }

  Widget _composer(ThemeData theme) {
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          border: Border(
            top: BorderSide(
              color: theme.colorScheme.outlineVariant,
              width: 0.5,
            ),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _input,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => _send(),
                decoration: InputDecoration(
                  hintText: 'Ask something...',
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(24),
                    borderSide: BorderSide.none,
                  ),
                  filled: true,
                  fillColor: theme.colorScheme.surfaceContainerHighest,
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              onPressed: _send,
              icon: const Icon(Icons.send),
              tooltip: 'Send',
            ),
          ],
        ),
      ),
    );
  }
}
