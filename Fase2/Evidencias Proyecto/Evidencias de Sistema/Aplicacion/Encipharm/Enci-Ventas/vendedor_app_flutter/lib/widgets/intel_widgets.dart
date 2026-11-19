import 'package:flutter/material.dart';

import '../models/intel_models.dart';
import '../services/intel_service.dart';
import '../theme/app_colors.dart';

Color priorityColor(String priority) {
  switch (priority.toLowerCase()) {
    case 'critical':
      return const Color(0xFFEF4444);
    case 'high':
      return AppColors.orange;
    case 'medium':
      return AppColors.blue;
    default:
      return AppColors.green;
  }
}

/// Aviso de datos sin conexion, compartido por alertas y fichas.
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({super.key, required this.cachedAt});
  final DateTime? cachedAt;

  @override
  Widget build(BuildContext context) {
    final text = cachedAt == null
        ? 'Sin conexión · mostrando datos guardados'
        : 'Sin conexión · datos del ${formatDateTime(cachedAt!)}';
    return Container(
      key: const Key('intel-offline-banner'),
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.orange.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.orange.withValues(alpha: 0.5)),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off, size: 16, color: AppColors.orange),
          const SizedBox(width: 8),
          Expanded(child: Text(text, style: const TextStyle(color: AppColors.orange, fontSize: 12))),
        ],
      ),
    );
  }
}

class IntelErrorView extends StatelessWidget {
  const IntelErrorView({super.key, required this.error, required this.onRetry});
  final IntelException error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final noAccess = error.kind == IntelErrorKind.noAccess;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(noAccess ? Icons.lock_outline : Icons.cloud_off, size: 48, color: AppColors.textMuted),
            const SizedBox(height: 12),
            Text(error.message,
                textAlign: TextAlign.center, style: const TextStyle(color: AppColors.textSoft, fontSize: 14)),
            if (!noAccess) ...[
              const SizedBox(height: 12),
              OutlinedButton(onPressed: onRetry, child: const Text('Reintentar')),
            ],
          ],
        ),
      ),
    );
  }
}
