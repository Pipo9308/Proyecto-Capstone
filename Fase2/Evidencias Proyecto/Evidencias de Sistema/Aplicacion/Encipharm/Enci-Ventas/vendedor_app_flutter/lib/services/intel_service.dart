import 'package:dio/dio.dart';

import '../models/intel_models.dart';
import 'api_service.dart';
import 'intel_cache.dart';

enum IntelErrorKind { noAccess, unavailable, other }

class IntelException implements Exception {
  const IntelException(this.kind, this.message);
  final IntelErrorKind kind;
  final String message;

  @override
  String toString() => message;
}

/// Resultado de una consulta; `fromCache` indica que no hubo red y se muestra la copia local.
class IntelResult<T> {
  const IntelResult(this.data, {this.fromCache = false, this.cachedAt});
  final T data;
  final bool fromCache;
  final DateTime? cachedAt;
}

abstract class IntelApi {
  Future<IntelResult<IntelAlertsPage>> fetchAlerts({
    String? priority,
    String? type,
    String? competitor,
    int offset = 0,
    int limit = 50,
  });
  Future<void> markRead(String alertId);
  Future<int> unreadCount();
  Future<IntelResult<List<ProductSummary>>> searchProducts(String query);
  Future<IntelResult<ProductSheet>> fetchSheet(String registro);
}

/// Habla solo con el backend de Ventas (`/inteligencia/*`), que consulta Enci-Intel
/// por detras. Si no hay red o Intel esta caido, usa la copia local.
class IntelService implements IntelApi {
  IntelService({IntelCache? cache}) : _cache = cache ?? IntelCache();

  final IntelCache _cache;

  static bool _isOffline(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionError:
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.sendTimeout:
        return true;
      default:
        final status = e.response?.statusCode;
        return status == 502 || status == 503 || status == 504;
    }
  }

  /// Convierte los errores de Dio en errores de dominio. `SIN_ACCESO` lo genera el
  /// interceptor de ApiService para cualquier 401/403.
  static IntelException _translate(Object error) {
    if (error is DioException) {
      if (error.message == 'SIN_ACCESO' || error.error == 'SIN_ACCESO') {
        return const IntelException(IntelErrorKind.noAccess, 'Tu cuenta no tiene acceso a Inteligencia.');
      }
      if (_isOffline(error)) {
        return const IntelException(
          IntelErrorKind.unavailable,
          'Enci-Intel no está disponible por ahora. El resto de la app sigue funcionando.',
        );
      }
    }
    return const IntelException(IntelErrorKind.other, 'No se pudo cargar la información. Intenta de nuevo.');
  }

  @override
  Future<IntelResult<IntelAlertsPage>> fetchAlerts({
    String? priority,
    String? type,
    String? competitor,
    int offset = 0,
    int limit = 50,
  }) async {
    final unfiltered = (priority ?? '').isEmpty && (type ?? '').isEmpty && (competitor ?? '').trim().isEmpty;
    try {
      final dio = await ApiService.authClient();
      final res = await dio.get('/inteligencia/alertas', queryParameters: {
        if ((priority ?? '').isNotEmpty) 'priority': priority,
        if ((type ?? '').isNotEmpty) 'type': type,
        if ((competitor ?? '').trim().isNotEmpty) 'competitor': competitor!.trim(),
        'limit': limit,
        'offset': offset,
      });
      final page = IntelAlertsPage.fromJson(Map<String, dynamic>.from(res.data as Map));
      if (unfiltered && offset == 0) await _cache.saveAlerts(page.alerts);
      return IntelResult(page);
    } catch (e) {
      final translated = _translate(e);
      if (translated.kind == IntelErrorKind.unavailable && offset == 0) {
        final cached = await _cache.loadAlerts();
        if (cached != null) {
          final filtered = IntelCache.applyFilters(cached.alerts, priority: priority, type: type, competitor: competitor);
          return IntelResult(
            IntelAlertsPage(alerts: filtered, total: filtered.length, hasMore: false),
            fromCache: true,
            cachedAt: cached.savedAt,
          );
        }
      }
      throw translated;
    }
  }

  @override
  Future<void> markRead(String alertId) async {
    await _cache.markAlertRead(alertId);
    try {
      final dio = await ApiService.authClient();
      await dio.patch('/inteligencia/alertas/$alertId/leida');
    } catch (_) {
      // Mejor esfuerzo: sin red, la lectura queda solo en el dispositivo.
    }
  }

  @override
  Future<int> unreadCount() async {
    try {
      final dio = await ApiService.authClient();
      final res = await dio.get('/inteligencia/alertas/no-leidas');
      return (res.data['no_leidas'] as num).toInt();
    } catch (e) {
      final cached = await _cache.loadAlerts();
      if (cached != null) return cached.alerts.where((a) => !a.leida).length;
      throw _translate(e);
    }
  }

  @override
  Future<IntelResult<List<ProductSummary>>> searchProducts(String query) async {
    try {
      final dio = await ApiService.authClient();
      final res = await dio.get('/inteligencia/productos', queryParameters: {'q': query.trim(), 'limit': 30});
      final items = (res.data['data'] as List)
          .map((e) => ProductSummary.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();
      return IntelResult(items);
    } catch (e) {
      final translated = _translate(e);
      if (translated.kind == IntelErrorKind.unavailable) {
        return IntelResult(await _cache.searchSheets(query), fromCache: true);
      }
      throw translated;
    }
  }

  @override
  Future<IntelResult<ProductSheet>> fetchSheet(String registro) async {
    try {
      final dio = await ApiService.authClient();
      final res = await dio.get('/inteligencia/productos/$registro/ficha');
      final sheet = ProductSheet.fromJson(Map<String, dynamic>.from(res.data['data'] as Map));
      await _cache.saveSheet(sheet);
      return IntelResult(sheet);
    } catch (e) {
      final translated = _translate(e);
      if (translated.kind == IntelErrorKind.unavailable) {
        final cached = await _cache.loadSheet(registro);
        if (cached != null) return IntelResult(cached.sheet, fromCache: true, cachedAt: cached.savedAt);
      }
      throw translated;
    }
  }
}
