import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_vendedor/models/intel_models.dart';
import 'package:flutter_vendedor/services/intel_cache.dart';
import 'package:shared_preferences/shared_preferences.dart';

IntelAlert _alert(int n, {String priority = 'medium', String? competitor, String subtype = 'NOTICIA', bool leida = false}) =>
    IntelAlert(
      id: 'a$n',
      title: 'Alerta $n',
      priority: priority,
      competitor: competitor,
      subtype: subtype,
      leida: leida,
      createdAt: DateTime.utc(2026, 10, 12, 10).subtract(Duration(minutes: n)),
    );

ProductSheet _sheet(String registro, {String? nombre, String? activo}) => ProductSheet(
      summary: ProductSummary(registro: registro, nombreComercial: nombre ?? 'Producto $registro', principioActivo: activo),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late IntelCache cache;
  final now = DateTime.utc(2026, 10, 12, 12);

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    cache = IntelCache();
  });

  group('alertas', () {
    test('sin datos guardados no hay cache', () async {
      expect(await cache.loadAlerts(), isNull);
    });

    test('guarda solo las 100 mas recientes y conserva el orden', () async {
      await cache.saveAlerts([for (var i = 0; i < 150; i++) _alert(i)], now: now);

      final cached = (await cache.loadAlerts())!;

      expect(cached.alerts.length, 100);
      expect(cached.alerts.first.id, 'a0');
      expect(cached.alerts.last.id, 'a99');
      expect(cached.savedAt, now);
    });

    test('marcar como leida actualiza la copia sin cambiar la fecha de descarga', () async {
      await cache.saveAlerts([_alert(1), _alert(2)], now: now);

      await cache.markAlertRead('a2');

      final cached = (await cache.loadAlerts())!;
      expect(cached.alerts.firstWhere((a) => a.id == 'a2').leida, isTrue);
      expect(cached.alerts.firstWhere((a) => a.id == 'a1').leida, isFalse);
      expect(cached.savedAt, now);
    });

    test('los filtros locales replican los del backend', () {
      final alerts = [
        _alert(1, priority: 'critical', competitor: 'ZOETIS CHILE S.A.', subtype: 'NEWSKU'),
        _alert(2, priority: 'medium', competitor: 'Drag Pharma'),
        _alert(3, priority: 'medium', competitor: 'AGROVET', subtype: 'CANCELACION'),
      ];

      ids(List<IntelAlert> list) => list.map((a) => a.id).toList();
      expect(ids(IntelCache.applyFilters(alerts, priority: 'medium')), ['a2', 'a3']);
      expect(ids(IntelCache.applyFilters(alerts, competitor: 'zoetis')), ['a1']);
      expect(ids(IntelCache.applyFilters(alerts, type: 'cancelacion')), ['a3']);
      expect(ids(IntelCache.applyFilters(alerts, priority: 'medium', competitor: 'drag')), ['a2']);
      expect(ids(IntelCache.applyFilters(alerts)), ['a1', 'a2', 'a3']);
    });
  });

  group('fichas', () {
    test('una ficha vista hace menos de 7 dias esta disponible', () async {
      await cache.saveSheet(_sheet('1001'), now: now.subtract(const Duration(days: 6)));

      expect((await cache.loadSheet('1001', now: now))?.sheet.summary.registro, '1001');
    });

    test('una ficha de mas de 7 dias ya no se usa', () async {
      await cache.saveSheet(_sheet('1001'), now: now.subtract(const Duration(days: 8)));

      expect(await cache.loadSheet('1001', now: now), isNull);
    });

    test('guardar una ficha nueva descarta las vencidas', () async {
      await cache.saveSheet(_sheet('vieja'), now: now.subtract(const Duration(days: 10)));
      await cache.saveSheet(_sheet('nueva'), now: now);

      expect(await cache.loadSheet('vieja', now: now), isNull);
      expect(await cache.loadSheet('nueva', now: now), isNotNull);
    });

    test('mantiene como maximo 30 fichas, eliminando las mas antiguas', () async {
      for (var i = 0; i < 32; i++) {
        await cache.saveSheet(_sheet('r$i'), now: now.subtract(Duration(hours: 40 - i)));
      }

      expect(await cache.loadSheet('r0', now: now), isNull);
      expect(await cache.loadSheet('r1', now: now), isNull);
      expect(await cache.loadSheet('r2', now: now), isNotNull);
      expect(await cache.loadSheet('r31', now: now), isNotNull);
    });

    test('busca entre las fichas guardadas y vigentes', () async {
      await cache.saveSheet(_sheet('1', nombre: 'Draxxin', activo: 'TULATROMICINA'), now: now);
      await cache.saveSheet(_sheet('2', nombre: 'Ivermax', activo: 'IVERMECTINA'), now: now);
      await cache.saveSheet(_sheet('3', nombre: 'Viejo', activo: 'IVERMECTINA'), now: now.subtract(const Duration(days: 9)));

      final found = await cache.searchSheets('ivermectina', now: now);

      expect(found.map((p) => p.registro), ['2']);
    });
  });

  test('clear borra alertas y fichas (cambio de usuario en el mismo dispositivo)', () async {
    await cache.saveAlerts([_alert(1)], now: now);
    await cache.saveSheet(_sheet('1001'), now: now);

    await cache.clear();

    expect(await cache.loadAlerts(), isNull);
    expect(await cache.loadSheet('1001', now: now), isNull);
  });
}
