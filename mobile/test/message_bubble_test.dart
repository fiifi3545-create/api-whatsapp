import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:companion/api/models.dart';
import 'package:companion/widgets/message_bubble.dart';

Widget _host(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  testWidgets('renders text body for a text message', (tester) async {
    final msg = Message(
      sessionKey: 's',
      userId: 'u',
      direction: MessageDirection.outgoing,
      text: 'library hours are 8 to 10',
    );
    await tester.pumpWidget(_host(MessageBubble(message: msg)));
    expect(find.text('library hours are 8 to 10'), findsOneWidget);
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('renders the document affordance for a document message', (tester) async {
    final msg = Message(
      sessionKey: 's',
      userId: 'u',
      direction: MessageDirection.incoming,
      text: 'transcript.pdf',
      mediaType: 'document',
      caption: 'transcript.pdf',
    );
    await tester.pumpWidget(_host(MessageBubble(message: msg)));
    expect(find.byIcon(Icons.attach_file), findsOneWidget);
    expect(find.text('transcript.pdf'), findsOneWidget);
  });

  testWidgets('renders an Image widget when mediaUrl + image type present', (tester) async {
    final msg = Message(
      sessionKey: 's',
      userId: 'u',
      direction: MessageDirection.incoming,
      text: 'my id',
      mediaUrl: 'https://example.test/image.jpg',
      mediaType: 'image',
      caption: 'my id',
    );
    await tester.pumpWidget(_host(MessageBubble(message: msg)));
    expect(find.byType(Image), findsOneWidget);
    expect(find.text('my id'), findsOneWidget);
  });

  testWidgets('outgoing and incoming messages align on opposite sides', (tester) async {
    final out = Message(
      sessionKey: 's', userId: 'u', direction: MessageDirection.outgoing, text: 'a',
    );
    final inc = Message(
      sessionKey: 's', userId: 'u', direction: MessageDirection.incoming, text: 'b',
    );
    await tester.pumpWidget(_host(
      Column(children: [MessageBubble(message: out), MessageBubble(message: inc)]),
    ));
    final aligns = tester.widgetList<Align>(find.byType(Align)).toList();
    expect(aligns.length, greaterThanOrEqualTo(2));
    expect(aligns.first.alignment, Alignment.centerLeft);
    expect(aligns[1].alignment, Alignment.centerRight);
  });
}
