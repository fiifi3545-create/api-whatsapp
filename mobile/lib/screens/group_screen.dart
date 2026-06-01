import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../agora/rtm_session.dart';
import '../api/client.dart';
import '../api/models.dart';
import '../state/app_config_state.dart';
import '../state/chat_state.dart';
import '../state/groups_state.dart';
import '../state/presence_state.dart';
import '../state/session.dart';
import '../widgets/invite_card.dart';
import '../widgets/message_bubble.dart';
import 'group_call_screen.dart';

class GroupScreen extends StatefulWidget {
  final Group group;
  const GroupScreen({super.key, required this.group});

  @override
  State<GroupScreen> createState() => _GroupScreenState();
}

class _GroupScreenState extends State<GroupScreen> {
  late Future<List<GroupMember>> _members;
  RtmSession? _rtmRef;

  @override
  void initState() {
    super.initState();
    _members = _loadMembers();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      // Backfill chat history (live updates come via Agora Chat SDK).
      context.read<ChatState>().loadGroup(widget.group.groupId);
      // Subscribe for live presence in this group. Stash the ref so dispose
      // can unsubscribe without needing `context` (which may be gone).
      final rtm = context.read<RtmSession>();
      _rtmRef = rtm;
      rtm.subscribeToGroup(widget.group.groupId);
    });
  }

  @override
  void dispose() {
    _rtmRef?.unsubscribeFromGroup(widget.group.groupId);
    super.dispose();
  }

  Future<List<GroupMember>> _loadMembers() =>
      context.read<ApiClient>().listGroupMembers(widget.group.groupId);

  Future<void> _refreshAll() async {
    setState(() {
      _members = _loadMembers();
    });
    await context.read<ChatState>().loadGroup(widget.group.groupId);
    await _members;
  }

  Future<void> _confirmDelete() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete group?'),
        content: Text('"${widget.group.name}" will be removed permanently.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton.tonal(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    final session = context.read<Session>();
    final ok = await context.read<GroupsState>().deleteGroup(
          groupId: widget.group.groupId,
          requesterId: session.userId ?? '',
        );
    if (!mounted) return;
    if (ok) {
      Navigator.of(context).pop();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Only the creator can delete this group.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = context.watch<Session>();
    final config = context.watch<AppConfigState>().config;
    final isCreator = session.userId == widget.group.creatorId;

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text(widget.group.name),
          actions: [
            IconButton(
              tooltip: 'Start group call',
              icon: const Icon(Icons.videocam_outlined),
              onPressed: () {
                Navigator.of(context).push(MaterialPageRoute(
                  builder: (_) => GroupCallScreen(group: widget.group),
                ));
              },
            ),
            if (isCreator)
              IconButton(
                tooltip: 'Delete group',
                icon: const Icon(Icons.delete_outline),
                onPressed: _confirmDelete,
              ),
          ],
          bottom: const TabBar(
            tabs: [
              Tab(icon: Icon(Icons.forum_outlined), text: 'Messages'),
              Tab(icon: Icon(Icons.group_outlined), text: 'Members'),
            ],
          ),
        ),
        body: TabBarView(
          children: [
            _MessagesTab(
              groupId: widget.group.groupId,
              groupName: widget.group.name,
              joinCode: widget.group.joinCode,
              whatsappBotNumber: config.whatsappBotNumber,
              currentUserId: session.userId ?? '',
              onRefresh: _refreshAll,
            ),
            _MembersTab(
              groupId: widget.group.groupId,
              groupName: widget.group.name,
              joinCode: widget.group.joinCode,
              whatsappBotNumber: config.whatsappBotNumber,
              creatorId: widget.group.creatorId,
              currentUserId: session.userId,
              members: _members,
              onRefresh: _refreshAll,
            ),
          ],
        ),
      ),
    );
  }
}

class _MessagesTab extends StatefulWidget {
  final String groupId;
  final String groupName;
  final String joinCode;
  final String whatsappBotNumber;
  final String currentUserId;
  final Future<void> Function() onRefresh;

  const _MessagesTab({
    required this.groupId,
    required this.groupName,
    required this.joinCode,
    required this.whatsappBotNumber,
    required this.currentUserId,
    required this.onRefresh,
  });

  @override
  State<_MessagesTab> createState() => _MessagesTabState();
}

class _MessagesTabState extends State<_MessagesTab> {
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();
  int _lastLen = 0;

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _send() {
    final text = _input.text.trim();
    if (text.isEmpty) return;
    _input.clear();
    context.read<ChatState>().sendToGroup(
          groupId: widget.groupId,
          text: text,
        );
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
    final chat = context.watch<ChatState>();
    final messages = chat.messagesFor(widget.groupId);
    final loading = chat.isLoading(widget.groupId);

    if (messages.length != _lastLen) {
      _lastLen = messages.length;
      _scrollToBottom();
    }

    return Column(
      children: [
        Expanded(child: _list(theme, loading, messages)),
        _composer(theme),
      ],
    );
  }

  Widget _list(ThemeData theme, bool loading, List<Message> messages) {
    if (loading && messages.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    return RefreshIndicator(
      onRefresh: widget.onRefresh,
      child: messages.isEmpty
          ? ListView(
              padding: EdgeInsets.zero,
              children: [
                InviteCard(
                  groupName: widget.groupName,
                  joinCode: widget.joinCode,
                  whatsappBotNumber: widget.whatsappBotNumber,
                ),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 32, vertical: 40),
                  child: Column(
                    children: [
                      Icon(Icons.forum_outlined, size: 56),
                      SizedBox(height: 12),
                      Text(
                        'No messages yet.',
                        textAlign: TextAlign.center,
                        style: TextStyle(fontWeight: FontWeight.w600),
                      ),
                      SizedBox(height: 4),
                      Text(
                        'Say hi to your group, or mention @bot to ask a question.',
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ],
            )
          : ListView.builder(
              controller: _scroll,
              padding: const EdgeInsets.symmetric(vertical: 8),
              itemCount: messages.length,
              itemBuilder: (_, i) => MessageBubble(
                message: messages[i],
                viewerId: widget.currentUserId,
              ),
            ),
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
                  hintText: 'Message the group...',
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

class _MembersTab extends StatelessWidget {
  final String groupId;
  final String groupName;
  final String joinCode;
  final String whatsappBotNumber;
  final String creatorId;
  final String? currentUserId;
  final Future<List<GroupMember>> members;
  final Future<void> Function() onRefresh;

  const _MembersTab({
    required this.groupId,
    required this.groupName,
    required this.joinCode,
    required this.whatsappBotNumber,
    required this.creatorId,
    required this.currentUserId,
    required this.members,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    final presence = context.watch<PresenceState>();
    final onlineHere = presence.onlineMembers(groupId);
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: FutureBuilder<List<GroupMember>>(
        future: members,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) {
            return ListView(children: [
              InviteCard(
                groupName: groupName,
                joinCode: joinCode,
                whatsappBotNumber: whatsappBotNumber,
              ),
              Padding(
                padding: const EdgeInsets.all(24),
                child: Text('Could not load members.\n${snap.error}',
                    textAlign: TextAlign.center),
              ),
            ]);
          }
          final list = snap.data ?? const [];
          // "You" are obviously online; count yourself among the visible
          // online users even before the RTM snapshot arrives.
          final onlineCount = list.where((m) =>
              m.userId == currentUserId || onlineHere.contains(m.userId)
          ).length;
          return ListView(
            padding: const EdgeInsets.only(bottom: 24),
            children: [
              InviteCard(
                groupName: groupName,
                joinCode: joinCode,
                whatsappBotNumber: whatsappBotNumber,
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 8),
                child: Row(
                  children: [
                    Text(
                      '${list.length} member${list.length == 1 ? '' : 's'}',
                      style: Theme.of(context).textTheme.titleSmall,
                    ),
                    const SizedBox(width: 8),
                    if (onlineCount > 0)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: Colors.green.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 6,
                              height: 6,
                              decoration: const BoxDecoration(
                                color: Colors.green,
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              '$onlineCount online',
                              style: const TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w600,
                                color: Colors.green,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
              ...list.map((m) => _MemberTile(
                    member: m,
                    isYou: m.userId == currentUserId,
                    isOnline: m.userId == currentUserId ||
                        onlineHere.contains(m.userId),
                  )),
            ],
          );
        },
      ),
    );
  }
}

class _MemberTile extends StatelessWidget {
  final GroupMember member;
  final bool isYou;
  final bool isOnline;
  const _MemberTile({
    required this.member,
    required this.isYou,
    required this.isOnline,
  });

  Color _color(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final palette = [
      scheme.primary,
      scheme.tertiary,
      scheme.secondary,
      Colors.teal,
      Colors.deepOrange,
      Colors.indigo,
    ];
    final hash = member.userId.codeUnits.fold<int>(0, (a, b) => a + b);
    return palette[hash % palette.length];
  }

  @override
  Widget build(BuildContext context) {
    final color = _color(context);
    final initial = member.displayName.trim().isEmpty
        ? '?'
        : member.displayName.trim()[0].toUpperCase();
    final scheme = Theme.of(context).colorScheme;
    return ListTile(
      leading: Stack(
        clipBehavior: Clip.none,
        children: [
          CircleAvatar(
            backgroundColor: color.withValues(alpha: 0.18),
            foregroundColor: color,
            child: Text(initial,
                style: const TextStyle(fontWeight: FontWeight.w700)),
          ),
          if (isOnline)
            Positioned(
              right: -1,
              bottom: -1,
              child: Container(
                width: 12,
                height: 12,
                decoration: BoxDecoration(
                  color: Colors.green,
                  shape: BoxShape.circle,
                  // 2-px ring in the surface color so the dot reads as a
                  // status indicator instead of part of the avatar.
                  border: Border.all(color: scheme.surface, width: 2),
                ),
              ),
            ),
        ],
      ),
      title: Row(
        children: [
          Flexible(
            child: Text(
              member.displayName,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          if (isYou) ...[
            const SizedBox(width: 6),
            const _Chip(label: 'You'),
          ],
          if (member.isCreator) ...[
            const SizedBox(width: 6),
            const _Chip(label: 'Creator', icon: Icons.shield_outlined),
          ],
        ],
      ),
      subtitle: member.name.isNotEmpty ? Text(member.userId) : null,
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final IconData? icon;
  const _Chip({required this.label, this.icon});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: scheme.secondaryContainer,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 12, color: scheme.onSecondaryContainer),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: scheme.onSecondaryContainer,
            ),
          ),
        ],
      ),
    );
  }
}
