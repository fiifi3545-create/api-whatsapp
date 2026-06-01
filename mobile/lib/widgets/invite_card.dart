import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';

class InviteCard extends StatelessWidget {
  final String groupName;
  final String joinCode;
  final String? whatsappBotNumber;

  const InviteCard({
    super.key,
    required this.groupName,
    required this.joinCode,
    this.whatsappBotNumber,
  });

  String _shareText() {
    final bot = (whatsappBotNumber ?? '').trim();
    final waLine = bot.isNotEmpty
        ? '\n\nMessage the study bot on WhatsApp: https://wa.me/$bot'
        : '';
    return 'Join my study group "$groupName" on the Student Chatbot.\n'
        'Open the app, tap +, choose "Join with code", and enter:\n\n'
        '$joinCode$waLine';
  }

  Future<void> _copy(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: joinCode));
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Code "$joinCode" copied to clipboard'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  Future<void> _share(BuildContext context) async {
    final box = context.findRenderObject() as RenderBox?;
    await Share.share(
      _shareText(),
      subject: 'Join $groupName',
      sharePositionOrigin: box != null
          ? box.localToGlobal(Offset.zero) & box.size
          : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.fromLTRB(12, 12, 12, 4),
      clipBehavior: Clip.antiAlias,
      child: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              scheme.primary,
              scheme.primary.withValues(alpha: 0.75),
            ],
          ),
        ),
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Invite a classmate',
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                    color: scheme.onPrimary.withValues(alpha: 0.85),
                  ),
            ),
            const SizedBox(height: 6),
            Text(
              'Share this code so they can join the group.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onPrimary.withValues(alpha: 0.85),
                  ),
            ),
            const SizedBox(height: 14),
            InkWell(
              onTap: () => _copy(context),
              borderRadius: BorderRadius.circular(12),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                decoration: BoxDecoration(
                  color: scheme.onPrimary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: scheme.onPrimary.withValues(alpha: 0.35),
                  ),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        joinCode,
                        style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                              color: scheme.onPrimary,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 2,
                              fontFeatures: const [FontFeature.tabularFigures()],
                            ),
                      ),
                    ),
                    Icon(Icons.copy_rounded, color: scheme.onPrimary),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton.tonalIcon(
                    onPressed: () => _share(context),
                    icon: const Icon(Icons.ios_share),
                    label: const Text('Share invite'),
                    style: FilledButton.styleFrom(
                      backgroundColor: scheme.onPrimary,
                      foregroundColor: scheme.primary,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filledTonal(
                  onPressed: () => _copy(context),
                  tooltip: 'Copy code',
                  style: IconButton.styleFrom(
                    backgroundColor: scheme.onPrimary.withValues(alpha: 0.15),
                    foregroundColor: scheme.onPrimary,
                  ),
                  icon: const Icon(Icons.copy_rounded),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
