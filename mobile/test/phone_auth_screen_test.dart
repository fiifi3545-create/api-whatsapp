import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:companion/api/client.dart';
import 'package:companion/screens/phone_auth_screen.dart';
import 'package:companion/screens/otp_screen.dart';

class _FakeApi extends ApiClient {
  _FakeApi();

  final List<String> requested = [];
  String? echoOtp = '654321';

  @override
  Future<String?> requestOtp(String phoneNumber) async {
    requested.add(phoneNumber);
    return echoOtp;
  }
}

Widget _host(ApiClient api) => Provider<ApiClient>.value(
      value: api,
      child: const MaterialApp(home: PhoneAuthScreen()),
    );

void main() {
  testWidgets('submits the phone number and pushes the OTP screen', (tester) async {
    final api = _FakeApi();
    await tester.pumpWidget(_host(api));

    await tester.enterText(find.byType(TextField), '233200000001');
    await tester.tap(find.text('Send code'));
    await tester.pumpAndSettle();

    expect(api.requested, ['233200000001']);
    expect(find.byType(OtpScreen), findsOneWidget);
  });

  testWidgets('does nothing when the field is empty', (tester) async {
    final api = _FakeApi();
    await tester.pumpWidget(_host(api));

    await tester.tap(find.text('Send code'));
    await tester.pumpAndSettle();

    expect(api.requested, isEmpty);
    expect(find.byType(OtpScreen), findsNothing);
  });
}
