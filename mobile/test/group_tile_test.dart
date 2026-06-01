import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:companion/api/models.dart';
import 'package:companion/widgets/group_tile.dart';

void main() {
  testWidgets('shows name, member count, and join code', (tester) async {
    final g = Group(
      groupId: 'g1',
      name: 'CS401',
      creatorId: 'u1',
      joinCode: 'ABC123',
      members: const ['u1', 'u2', 'u3'],
    );

    var tapped = false;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: GroupTile(group: g, onTap: () => tapped = true),
      ),
    ));

    expect(find.text('CS401'), findsOneWidget);
    expect(find.textContaining('3 members'), findsOneWidget);
    expect(find.textContaining('ABC123'), findsOneWidget);

    await tester.tap(find.byType(InkWell).first);
    await tester.pumpAndSettle();
    expect(tapped, isTrue);
  });

  testWidgets('uses singular member when there is exactly one', (tester) async {
    final g = Group(
      groupId: 'g1', name: 'Solo', creatorId: 'u1', joinCode: 'X', members: const ['u1'],
    );
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: GroupTile(group: g, onTap: () {})),
    ));
    expect(find.textContaining('1 member'), findsOneWidget);
    expect(find.textContaining('1 members'), findsNothing);
  });
}
