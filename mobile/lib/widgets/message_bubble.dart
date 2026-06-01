import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../api/models.dart';

enum _BubbleRole { self, bot, other }

class MessageBubble extends StatelessWidget {
  final Message message;
  /// When set, used to determine whether the current viewer authored the
  /// message (so it renders as "self" on the right). In 1:1 bot chat this can
  /// be null — direction alone determines orientation.
  final String? viewerId;

  const MessageBubble({super.key, required this.message, this.viewerId});

  _BubbleRole get _role {
    if (message.isFromBot) return _BubbleRole.bot;
    if (viewerId != null && message.isFromViewer(viewerId!)) {
      return _BubbleRole.self;
    }
    // No viewerId provided → fall back to direction. 1:1 bot screen flow.
    if (viewerId == null && message.direction == MessageDirection.incoming) {
      return _BubbleRole.self;
    }
    if (viewerId == null && message.direction == MessageDirection.outgoing) {
      return _BubbleRole.bot;
    }
    return _BubbleRole.other;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final role = _role;

    // Self (right, green/tertiary), bot (left, blue/primary), other student
    // (left, neutral surfaceContainerHighest).
    final isSelf = role == _BubbleRole.self;
    final alignment = isSelf ? Alignment.centerRight : Alignment.centerLeft;
    final (color, textColor) = switch (role) {
      _BubbleRole.self => (theme.colorScheme.tertiary, theme.colorScheme.onTertiary),
      _BubbleRole.bot => (theme.colorScheme.primary, theme.colorScheme.onPrimary),
      _BubbleRole.other => (
          theme.colorScheme.surfaceContainerHighest,
          theme.colorScheme.onSurface,
        ),
    };
    final radius = BorderRadius.only(
      topLeft: const Radius.circular(20),
      topRight: const Radius.circular(20),
      bottomLeft: Radius.circular(isSelf ? 20 : 4),
      bottomRight: Radius.circular(isSelf ? 4 : 20),
    );

    final showSenderLabel = role == _BubbleRole.other ||
        (role == _BubbleRole.bot && (message.senderName.isNotEmpty));

    return Align(
      alignment: alignment,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4, horizontal: 12),
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 14),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.78,
        ),
        decoration: BoxDecoration(
          color: color,
          borderRadius: radius,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (showSenderLabel) ...[
              Text(
                role == _BubbleRole.bot
                    ? (message.senderName.isNotEmpty ? message.senderName : 'Bot')
                    : (message.senderName.isNotEmpty
                        ? message.senderName
                        : message.senderId),
                style: theme.textTheme.labelSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: textColor.withValues(alpha: 0.9),
                ),
              ),
              const SizedBox(height: 4),
            ],
            if (message.hasImage) ...[
              ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: _ImageWithFallback(mediaId: message.mediaUrl!),
              ),
              if ((message.caption ?? '').isNotEmpty) const SizedBox(height: 8),
            ] else if (message.mediaType == 'document') ...[
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.attach_file, size: 18, color: textColor),
                  const SizedBox(width: 6),
                  Flexible(
                    child: Text(
                      message.caption ?? 'Document',
                      style: TextStyle(color: textColor, fontStyle: FontStyle.italic),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
            ],
            if (_displayText.isNotEmpty)
              Text(_displayText, style: TextStyle(color: textColor)),
            if (message.createdAt != null) ...[
              const SizedBox(height: 4),
              Text(
                DateFormat.Hm().format(message.createdAt!.toLocal()),
                style: theme.textTheme.bodySmall?.copyWith(
                  color: textColor.withValues(alpha: 0.7),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String get _displayText {
    if (message.hasImage) return message.caption ?? '';
    if (message.mediaType == 'document') {
      return message.text == message.caption ? '' : message.text;
    }
    return message.text;
  }
}

class _ImageWithFallback extends StatelessWidget {
  /// WhatsApp media id stored on the Message; resolved to a proxy URL at render
  /// time using the in-tree ApiClient. If no ApiClient is in the tree (e.g.
  /// stand-alone widget tests), the media id is treated as a full URL.
  final String mediaId;
  const _ImageWithFallback({required this.mediaId});

  @override
  Widget build(BuildContext context) {
    final api = context.read<ApiClient?>();
    final url = api != null ? api.mediaProxyUrl(mediaId) : mediaId;
    final headers = api?.mediaHeaders();

    return Image.network(
      url,
      headers: headers,
      fit: BoxFit.cover,
      loadingBuilder: (_, child, progress) {
        if (progress == null) return child;
        return const SizedBox(
          height: 120,
          width: 200,
          child: Center(child: CircularProgressIndicator()),
        );
      },
      errorBuilder: (_, _, _) => Container(
        height: 80,
        width: 200,
        alignment: Alignment.center,
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: const [
            Icon(Icons.broken_image_outlined),
            SizedBox(width: 8),
            Text('Image unavailable'),
          ],
        ),
      ),
    );
  }
}
