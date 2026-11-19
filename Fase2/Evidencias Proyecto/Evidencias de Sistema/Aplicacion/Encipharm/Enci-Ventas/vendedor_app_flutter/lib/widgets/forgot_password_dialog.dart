import 'package:flutter/material.dart';

import '../theme/app_colors.dart';

/// Pide al administrador un enlace para crear una contraseña nueva; devuelve el mensaje a mostrar.
typedef PasswordResetRequester = Future<String> Function(String email);

class ForgotPasswordDialog extends StatefulWidget {
  const ForgotPasswordDialog({super.key, required this.initialEmail, required this.requester});
  final String initialEmail;
  final PasswordResetRequester requester;

  @override
  State<ForgotPasswordDialog> createState() => _ForgotPasswordDialogState();
}

class _ForgotPasswordDialogState extends State<ForgotPasswordDialog> {
  late final TextEditingController _email = TextEditingController(text: widget.initialEmail);
  bool _sending = false;
  String? _message;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    setState(() {
      _sending = true;
      _error = null;
      _message = null;
    });
    try {
      final message = await widget.requester(_email.text);
      if (mounted) setState(() => _message = message);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppColors.card,
      title: const Text('Restablecer contraseña', style: TextStyle(color: Colors.white)),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Tu administrador recibirá la solicitud y te enviará un enlace para crear una contraseña nueva.',
            style: TextStyle(color: AppColors.textSoft, fontSize: 13),
          ),
          const SizedBox(height: 12),
          TextField(
            key: const Key('forgot-email'),
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            style: const TextStyle(color: Colors.white),
            decoration: const InputDecoration(labelText: 'Correo electrónico'),
          ),
          if (_message != null) ...[
            const SizedBox(height: 12),
            Text(_message!, key: const Key('forgot-message'), style: const TextStyle(color: AppColors.green)),
          ],
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, key: const Key('forgot-error'), style: const TextStyle(color: Colors.redAccent)),
          ],
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cerrar')),
        FilledButton(
          key: const Key('forgot-send'),
          onPressed: _sending || _message != null ? null : _send,
          child: Text(_sending ? 'Enviando...' : 'Enviar solicitud'),
        ),
      ],
    );
  }
}
