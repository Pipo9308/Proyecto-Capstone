import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_vendedor/models/intel_models.dart';

void main() {
  group('parseUtc', () {
    test('una fecha sin zona se interpreta como UTC, no como hora local', () {
      final parsed = parseUtc('2026-10-12T17:42:27.813000')!;
      expect(parsed.isUtc, isTrue);
      expect(parsed.hour, 17);
    });

    test('respeta el offset explicito', () {
      expect(parseUtc('2026-10-12T14:42:27-03:00'), parseUtc('2026-10-12T17:42:27+00:00'));
      expect(parseUtc('2026-10-12T17:42:27Z'), parseUtc('2026-10-12T17:42:27+00:00'));
    });

    test('valores vacios dan null', () {
      expect(parseUtc(null), isNull);
      expect(parseUtc(''), isNull);
    });
  });

  group('timeAgo', () {
    final now = DateTime.utc(2026, 10, 12, 12, 0);

    test('minutos, horas y dias', () {
      expect(timeAgo(now.subtract(const Duration(seconds: 20)), now: now), 'ahora');
      expect(timeAgo(now.subtract(const Duration(minutes: 5)), now: now), 'hace 5 min');
      expect(timeAgo(now.subtract(const Duration(hours: 3)), now: now), 'hace 3 h');
      expect(timeAgo(now.subtract(const Duration(days: 2)), now: now), 'hace 2 d');
    });

    test('mas de 30 dias muestra la fecha y sin fecha queda vacio', () {
      expect(timeAgo(DateTime.utc(2026, 8, 1, 12), now: now), isNot(startsWith('hace')));
      expect(timeAgo(null, now: now), '');
    });
  });

  test('etiquetas de prioridad y tipo', () {
    expect(priorityLabel('critical'), 'Crítica');
    expect(priorityLabel('HIGH'), 'Alta');
    expect(priorityLabel('medium'), 'Media');
    expect(priorityLabel('low'), 'Baja');
    expect(alertTypeLabel('NEWSKU'), 'Nuevo registro');
    expect(alertTypeLabel('CANCELACION'), 'Cancelación');
    expect(alertTypeLabel('NOTICIA'), 'Noticia');
  });

  group('IntelAlert', () {
    test('lee el contrato del backend y usa body si no hay description', () {
      final alert = IntelAlert.fromJson({
        'id': 'comp_noticia_ab',
        'title': 'Nueva publicación',
        'priority': 'MEDIUM',
        'competitor': 'Drag Pharma',
        'subtype': 'NOTICIA',
        'body': 'Resumen de la noticia',
        'created_at': '2026-10-12T17:42:27+00:00',
        'data': {'empresa': 'DRAG PHARMA'},
        'leida': true,
      });

      expect(alert.priority, 'medium');
      expect(alert.description, 'Resumen de la noticia');
      expect(alert.leida, isTrue);
      expect(alert.data['empresa'], 'DRAG PHARMA');
      expect(alert.createdAt, DateTime.utc(2026, 10, 12, 17, 42, 27));
    });

    test('toJson y fromJson son inversos (lo usa la copia local)', () {
      final original = IntelAlert.fromJson({
        'id': 'a1',
        'title': 'T',
        'priority': 'critical',
        'created_at': '2026-10-12T10:00:00+00:00',
        'data': {'k': 'v'},
      });

      final copy = IntelAlert.fromJson(original.toJson());

      expect(copy.id, original.id);
      expect(copy.priority, original.priority);
      expect(copy.createdAt, original.createdAt);
      expect(copy.data, original.data);
    });

    test('copyWith solo cambia la lectura', () {
      final alert = IntelAlert.fromJson({'id': 'a1', 'title': 'T', 'priority': 'low'});
      final read = alert.copyWith(leida: true);
      expect(read.leida, isTrue);
      expect(read.title, 'T');
    });
  });

  group('ProductSummary / ProductSheet', () {
    final summary = ProductSummary.fromJson({
      'registro': '1001',
      'nombre_comercial': 'Draxxin',
      'principio_activo': 'TULATROMICINA',
      'titular': 'ZOETIS CHILE S.A.',
    });

    test('busca por nombre, principio activo, titular y registro sin distinguir mayusculas', () {
      expect(summary.matches('draxx'), isTrue);
      expect(summary.matches('tulatro'), isTrue);
      expect(summary.matches('zoetis'), isTrue);
      expect(summary.matches('1001'), isTrue);
      expect(summary.matches('ivermectina'), isFalse);
    });

    test('la ficha lee precios vacios y equivalente nulo', () {
      final sheet = ProductSheet.fromJson({
        'registro': '1001',
        'nombre_comercial': 'Draxxin',
        'actualizado': '2026-10-01T10:00:00+00:00',
        'registro_sag': {'Especies': 'BOVINO'},
        'alertas': [
          {'id': 'sag_newsku_1001', 'titulo': 'Nuevo registro SAG'}
        ],
        'precios': [],
        'equivalente_encipharm': null,
        'fuentes': [
          {'dato': 'registro_sag', 'origen': 'SAG (Enci-Intel)', 'fecha': '2026-10-01T10:00:00+00:00'}
        ],
      });

      expect(sheet.precios, isEmpty);
      expect(sheet.equivalenteEncipharm, isNull);
      expect(sheet.registroSag['Especies'], 'BOVINO');
      expect(sheet.alertas.single['id'], 'sag_newsku_1001');
      expect(sheet.actualizado, DateTime.utc(2026, 10, 1, 10));
    });
  });
}
