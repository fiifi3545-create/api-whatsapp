import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../api/client.dart';
import '../state/session.dart';

class OtpScreen extends StatefulWidget {
  final String phoneNumber;

  /// Backend echoes the OTP in dev mode (OTP_ECHO_IN_RESPONSE=true). If set,
  /// the screen prefills it so you don't have to read your own server logs.
  final String? devOtp;

  const OtpScreen({super.key, required this.phoneNumber, this.devOtp});

  @override
  State<OtpScreen> createState() => _OtpScreenState();
}

class _OtpScreenState extends State<OtpScreen> {
  late final TextEditingController _codeCtrl;
  bool _verifying = false;

  @override
  void initState() {
    super.initState();
    _codeCtrl = TextEditingController(text: widget.devOtp ?? '');
  }

  @override
  void dispose() {
    _codeCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final code = _codeCtrl.text.trim();
    if (code.length < 4) return;

    setState(() => _verifying = true);
    final api = context.read<ApiClient>();
    final session = context.read<Session>();
    try {
      final token = await api.verifyOtp(phoneNumber: widget.phoneNumber, code: code);
      api.token = token;
      await session.setAuthenticated(
        userId: widget.phoneNumber,
        token: token,
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _verifying = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Verification failed: $e')),
      );
      return;
    }
    if (!mounted) return;
    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Enter code')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'A 6-digit code was sent to ${widget.phoneNumber}.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (widget.devOtp != null) ...[
              const SizedBox(height: 8),
              Text(
                'Dev mode: code prefilled below.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
            const SizedBox(height: 16),
            TextField(
              controller: _codeCtrl,
              autofocus: true,
              keyboardType: TextInputType.number,
              maxLength: 6,
              decoration: const InputDecoration(
                labelText: 'OTP',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _verifying ? null : _submit,
              child: Text(_verifying ? 'Verifying…' : 'Verify'),
            ),
          ],
        ),
      ),
    );
  }
}
