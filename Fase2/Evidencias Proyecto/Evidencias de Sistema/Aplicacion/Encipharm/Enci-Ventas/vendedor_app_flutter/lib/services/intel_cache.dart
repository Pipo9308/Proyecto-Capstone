import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/intel_models.dart';

class CachedAlerts {
  const CachedAlerts(this.alerts, this.savedAt);
  final List<IntelAlert> alerts;
  final DateTime savedAt;
}

class CachedSheet {
  const CachedSheet(this.sheet, this.savedAt);
  final ProductSheet sheet;
  final DateTime savedAt;
}

/// Copia local para usar Inteligencia sin senal: las ultimas 100 alertas y las
/// fichas vistas en los ultimos 7 dias. Todo falla en silencio: la cache nunca
/// debe romper la pantalla.
class IntelCache {
  static const _kAlerts = 'intel_alerts_v1';
  static const _kSheets = 'intel_sheets_v1';
  static const maxAlerts = 100;
  static const maxSheets = 30;
  static const sheetTtl = Duration(days: 7);

  Future<void> saveAlerts(List<IntelAlert> alerts, {DateTime? now}) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final newest = alerts.take(maxAlerts).map((a) => a.toJson()).toList();
      await prefs.setString(
        _kAlerts,
        jsonEncode({'savedAt': (now ?? DateTime.now()).toUtc().toIso8601String(), 'alerts': newest}),
      );
    } catch (_) {}
  }

  Future<CachedAlerts?> loadAlerts() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_kAlerts);
      if (raw == null) return null;
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      final savedAt = parseUtc(decoded['savedAt']);
      if (savedAt == null) return null;
      final alerts = (decoded['alerts'] as List)
          .map((e) => IntelAlert.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();
      return CachedAlerts(alerts, savedAt);
    } catch (_) {
      return null;
    }
  }

  /// Marca una alerta como leida en la copia local (sin conexion no hay otra forma).
  Future<void> markAlertRead(String alertId) async {
    final cached = await loadAlerts();
    if (cached == null) return;
    final updated = cached.alerts.map((a) => a.id == alertId ? a.copyWith(leida: true) : a).toList();
    await saveAlerts(updated, now: cached.savedAt);
  }

  Future<void> saveSheet(ProductSheet sheet, {DateTime? now}) async {
    try {
      final moment = now ?? DateTime.now();
      final prefs = await SharedPreferences.getInstance();
      final sheets = await _readSheets(prefs);
      sheets[sheet.summary.registro] = {
        'savedAt': moment.toUtc().toIso8601String(),
        'sheet': sheet.toJson(),
      };
      _prune(sheets, moment);
      await prefs.setString(_kSheets, jsonEncode(sheets));
    } catch (_) {}
  }

  Future<CachedSheet?> loadSheet(String registro, {DateTime? now}) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final entry = (await _readSheets(prefs))[registro];
      return _toCached(entry, now ?? DateTime.now());
    } catch (_) {
      return null;
    }
  }

  /// Fichas guardadas y vigentes que coinciden con la busqueda (busqueda sin conexion).
  Future<List<ProductSummary>> searchSheets(String query, {DateTime? now}) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final moment = now ?? DateTime.now();
      final found = <ProductSummary>[];
      for (final entry in (await _readSheets(prefs)).values) {
        final cached = _toCached(entry, moment);
        if (cached != null && cached.sheet.summary.matches(query)) found.add(cached.sheet.summary);
      }
      return found;
    } catch (_) {
      return const [];
    }
  }

  Future<void> clear() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_kAlerts);
      await prefs.remove(_kSheets);
    } catch (_) {}
  }

  /// Aplica en el dispositivo los mismos filtros que el backend (para el modo sin conexion).
  static List<IntelAlert> applyFilters(
    List<IntelAlert> alerts, {
    String? priority,
    String? type,
    String? competitor,
  }) {
    return alerts.where((a) {
      if (priority != null && priority.isNotEmpty && a.priority != priority.toLowerCase()) return false;
      if (type != null && type.isNotEmpty) {
        final wanted = type.toLowerCase();
        final matches = (a.type ?? '').toLowerCase() == wanted || (a.subtype ?? '').toLowerCase() == wanted;
        if (!matches) return false;
      }
      if (competitor != null && competitor.trim().isNotEmpty) {
        if (!(a.competitor ?? '').toLowerCase().contains(competitor.trim().toLowerCase())) return false;
      }
      return true;
    }).toList();
  }

  Future<Map<String, dynamic>> _readSheets(SharedPreferences prefs) async {
    final raw = prefs.getString(_kSheets);
    if (raw == null) return {};
    return Map<String, dynamic>.from(jsonDecode(raw) as Map);
  }

  CachedSheet? _toCached(dynamic entry, DateTime now) {
    if (entry is! Map) return null;
    final savedAt = parseUtc(entry['savedAt']);
    if (savedAt == null || now.toUtc().difference(savedAt) > sheetTtl) return null;
    return CachedSheet(ProductSheet.fromJson(Map<String, dynamic>.from(entry['sheet'] as Map)), savedAt);
  }

  void _prune(Map<String, dynamic> sheets, DateTime now) {
    sheets.removeWhere((_, entry) => _toCached(entry, now) == null);
    if (sheets.length <= maxSheets) return;
    final byAge = sheets.entries.toList()
      ..sort((a, b) => (parseUtc(a.value['savedAt']) ?? DateTime(0))
          .compareTo(parseUtc(b.value['savedAt']) ?? DateTime(0)));
    for (final entry in byAge.take(sheets.length - maxSheets)) {
      sheets.remove(entry.key);
    }
  }
}
