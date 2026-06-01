import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import 'otp_screen.dart';

class PhoneAuthScreen extends StatefulWidget {
  const PhoneAuthScreen({super.key});

  @override
  State<PhoneAuthScreen> createState() => _PhoneAuthScreenState();
}

class _PhoneAuthScreenState extends State<PhoneAuthScreen> {
  final _phoneCtrl = TextEditingController();
  bool _sending = false;

  @override
  void dispose() {
    _phoneCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final phone = _phoneCtrl.text.trim();
    if (phone.isEmpty) return;
    setState(() => _sending = true);
    final api = context.read<ApiClient>();
    String? devOtp;
    try {
      devOtp = await api.requestOtp(phone);
    } catch (e) {
      if (!mounted) return;
      setState(() => _sending = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not request OTP: $e')),
      );
      return;
    }
    if (!mounted) return;
    setState(() => _sending = false);
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => OtpScreen(phoneNumber: phone, devOtp: devOtp),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sign in')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              "We'll send a 6-digit code to your WhatsApp number to confirm it's you.",
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _phoneCtrl,
              autofocus: true,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'WhatsApp number',
                helperText: 'Country code + number, no leading + (e.g. 233200000000).',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _sending ? null : _submit,
              child: Text(_sending ? 'Sending…' : 'Send code'),
            ),
          ],
        ),
      ),
    );
  }
}
