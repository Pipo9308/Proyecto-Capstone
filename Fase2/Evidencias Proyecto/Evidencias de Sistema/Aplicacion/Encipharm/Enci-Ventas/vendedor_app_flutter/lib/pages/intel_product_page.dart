import 'package:flutter/material.dart';

import '../models/intel_models.dart';
import '../services/intel_service.dart';
import '../theme/app_colors.dart';
import '../widgets/intel_widgets.dart';

/// Ficha de un producto del registro SAG: datos oficiales, alertas relacionadas,
/// precios conocidos y producto Encipharm equivalente (cada dato con su origen y fecha).
class IntelProductPage extends StatefulWidget {
  const IntelProductPage({super.key, required this.registro, required this.api});
  final String registro;
  final IntelApi api;

  @override
  State<IntelProductPage> createState() => _IntelProductPageState();
}

class _IntelProductPageState extends State<IntelProductPage> {
  IntelResult<ProductSheet>? _result;
  IntelException? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await widget.api.fetchSheet(widget.registro);
      if (!mounted) return;
      setState(() {
        _result = result;
        _loading = false;
      });
    } on IntelException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: const Color(0xFF0F172A),
        foregroundColor: Colors.white,
        title: const Text('Ficha SAG'),
      ),
      body: SafeArea(child: _buildBody()),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator(color: AppColors.teal));
    if (_error != null) return IntelErrorView(error: _error!, onRetry: _load);
    final result = _result!;
    final sheet = result.data;
    final summary = sheet.summary;
    return ListView(
      key: const Key('intel-product-sheet'),
      padding: const EdgeInsets.all(16),
      children: [
        if (result.fromCache) OfflineBanner(cachedAt: result.cachedAt),
        Text(summary.nombreComercial ?? summary.registro,
            style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        Text('Registro SAG ${summary.registro}${(summary.estado ?? '') == 'cancelado' ? ' · CANCELADO' : ''}',
            style: const TextStyle(color: AppColors.textMuted)),
        const SizedBox(height: 16),
        _Section(title: 'Registro SAG', children: [
          _Row('Principio activo', summary.principioActivo),
          _Row('Titular', summary.titular),
          _Row('Fabricante', summary.fabricante),
          _Row('Clasificación', summary.clasificacion),
          for (final entry in sheet.registroSag.entries.where((e) => _extraField(e.key)))
            _Row(entry.key, entry.value?.toString()),
        ]),
        _Section(title: 'Alertas relacionadas', children: [
          if (sheet.alertas.isEmpty)
            const Text('Sin alertas para este producto.', style: TextStyle(color: AppColors.textMuted))
          else
            for (final alert in sheet.alertas)
              _Row(alertTypeLabel(alert['tipo']?.toString()), alert['titulo']?.toString()),
        ]),
        _Section(title: 'Precios conocidos', children: [
          if (sheet.precios.isEmpty)
            const Text('Aún no hay precios registrados para este producto.',
                style: TextStyle(color: AppColors.textMuted))
          else
            for (final price in sheet.precios)
              _Row(price['fuente']?.toString() ?? 'Precio', '${price['precio']} ${price['moneda'] ?? ''}'.trim()),
        ]),
        _Section(title: 'Equivalente Encipharm', children: [
          Text(
            sheet.equivalenteEncipharm == null
                ? 'Sin producto equivalente registrado.'
                : (sheet.equivalenteEncipharm!['nombre']?.toString() ?? 'Equivalente registrado'),
            style: const TextStyle(color: AppColors.textMuted),
          ),
        ]),
        _Section(title: 'Fuentes', children: [
          for (final source in sheet.fuentes)
            _Row(
              source['dato']?.toString() ?? '',
              [
                source['origen']?.toString(),
                if (parseUtc(source['fecha']) != null) 'actualizado ${formatDate(parseUtc(source['fecha'])!)}',
              ].where((e) => (e ?? '').isNotEmpty).join(' · '),
            ),
        ]),
      ],
    );
  }

  // Los campos ya mostrados arriba no se repiten en el detalle del registro.
  static const _shown = {
    'Registro',
    'Nombre comercial',
    'Nombre Genérico',
    'Importador o Registrante',
    'Empresa Fabricante',
    'Clasificación',
  };

  bool _extraField(String key) => !_shown.contains(key);
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.children});
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(color: AppColors.teal, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          ...children,
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value);
  final String label;
  final String? value;

  @override
  Widget build(BuildContext context) {
    if ((value ?? '').trim().isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 120, child: Text(label, style: const TextStyle(color: AppColors.textMuted, fontSize: 12))),
          Expanded(child: Text(value!, style: const TextStyle(color: Colors.white, fontSize: 13))),
        ],
      ),
    );
  }
}
