import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../state/groups_state.dart';
import '../state/session.dart';
import '../widgets/group_tile.dart';
import 'create_group_screen.dart';
import 'group_screen.dart';
import 'join_group_screen.dart';
import 'messages_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
  }

  Future<void> _refresh() async {
    final session = context.read<Session>();
    if (session.userId != null) {
      await context.read<GroupsState>().refresh(session.userId!);
    }
  }

  Future<void> _openSheet() async {
    final action = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const CircleAvatar(child: Icon(Icons.add)),
              title: const Text('Create new group'),
              subtitle: const Text('You become the creator and get a join code.'),
              onTap: () => Navigator.of(context).pop('create'),
            ),
            ListTile(
              leading: const CircleAvatar(child: Icon(Icons.key)),
              title: const Text('Join with code'),
              subtitle: const Text('Enter a code shared by a classmate.'),
              onTap: () => Navigator.of(context).pop('join'),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
    if (action == null || !mounted) return;
    final route = action == 'create'
        ? MaterialPageRoute(builder: (_) => const CreateGroupScreen())
        : MaterialPageRoute(builder: (_) => const JoinGroupScreen());
    await Navigator.of(context).push(route);
    _refresh();
  }

  @override
  Widget build(BuildContext context) {
    final groups = context.watch<GroupsState>();
    final session = context.watch<Session>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Study groups'),
        actions: [
          IconButton(
            tooltip: 'Direct messages',
            icon: const Icon(Icons.chat_bubble_outline),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const MessagesScreen()),
            ),
          ),
          IconButton(
            tooltip: 'Settings',
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: _body(context, groups, session),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openSheet,
        icon: const Icon(Icons.add),
        label: const Text('New group'),
      ),
    );
  }

  Widget _body(BuildContext context, GroupsState groups, Session session) {
    if (groups.isLoading && groups.groups.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (groups.error != null && groups.groups.isEmpty) {
      return ListView(
        children: [
          const SizedBox(height: 80),
          Icon(Icons.cloud_off_outlined,
              size: 56,
              color: Theme.of(context).colorScheme.onSurfaceVariant),
          const SizedBox(height: 12),
          const Center(
            child: Text(
              'Could not load groups.',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          const SizedBox(height: 4),
          Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Text(
                '${groups.error}',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ),
          const SizedBox(height: 24),
          Center(
            child: FilledButton.tonalIcon(
              onPressed: _refresh,
              icon: const Icon(Icons.refresh),
              label: const Text('Try again'),
            ),
          ),
        ],
      );
    }
    if (groups.groups.isEmpty) {
      return ListView(
        children: [
          const SizedBox(height: 64),
          Container(
            width: 96,
            height: 96,
            margin: const EdgeInsets.symmetric(horizontal: 24),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Theme.of(context)
                  .colorScheme
                  .primaryContainer
                  .withValues(alpha: 0.5),
            ),
            child: Icon(
              Icons.groups_2_outlined,
              size: 48,
              color: Theme.of(context).colorScheme.primary,
            ),
          ).centeredHorizontally(),
          const SizedBox(height: 20),
          const Center(
            child: Text(
              'No study groups yet',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
            ),
          ),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 40),
            child: Text(
              'Create a group and share the join code with classmates, or join one with a code you were given.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
          ),
          const SizedBox(height: 24),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 48),
            child: FilledButton.icon(
              onPressed: _openSheet,
              icon: const Icon(Icons.add),
              label: const Text('Create or join a group'),
            ),
          ),
        ],
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: groups.groups.length,
      itemBuilder: (_, i) {
        final g = groups.groups[i];
        return GroupTile(
          group: g,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => GroupScreen(group: g)),
          ),
        );
      },
    );
  }
}

extension _Center on Widget {
  Widget centeredHorizontally() => Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [this],
      );
}
