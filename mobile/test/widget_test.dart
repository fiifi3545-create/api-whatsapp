import 'package:flutter_test/flutter_test.dart';

import 'package:companion/api/models.dart';

void main() {
  group('Message.fromJson', () {
    test('parses an incoming text message', () {
      final msg = Message.fromJson({
        'session_key': 's',
        'user_id': 'u1',
        'direction': 'in',
        'text': 'hi',
        'created_at': '2026-05-30T12:00:00+00:00',
      });
      expect(msg.direction, MessageDirection.incoming);
      expect(msg.text, 'hi');
      expect(msg.hasImage, isFalse);
      expect(msg.createdAt, isNotNull);
    });

    test('parses an outgoing text message', () {
      final msg = Message.fromJson({
        'session_key': 's',
        'user_id': 'u1',
        'direction': 'out',
        'text': 'hello',
      });
      expect(msg.direction, MessageDirection.outgoing);
      expect(msg.createdAt, isNull);
    });

    test('parses an image message with caption', () {
      final msg = Message.fromJson({
        'session_key': 's',
        'user_id': 'u1',
        'direction': 'in',
        'text': 'my receipt',
        'media_url': 'media-99',
        'media_type': 'image',
        'caption': 'my receipt',
      });
      expect(msg.hasImage, isTrue);
      expect(msg.mediaUrl, 'media-99');
      expect(msg.caption, 'my receipt');
    });
  });

  group('Group.fromJson', () {
    test('handles missing members list', () {
      final g = Group.fromJson({
        'group_id': 'g1',
        'name': 'CS401',
        'creator_id': 'u1',
        'join_code': 'CODE',
      });
      expect(g.members, isEmpty);
      expect(g.name, 'CS401');
    });
  });
}
