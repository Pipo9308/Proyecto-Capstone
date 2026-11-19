import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_vendedor/models/intel_models.dart';
import 'package:flutter_vendedor/pages/inteligencia_page.dart';
import 'package:flutter_vendedor/models/chat_models.dart';
import 'package:flutter_vendedor/services/competencia_chat_service.dart';
import 'package:flutter_vendedor/services/intel_service.dart';

class FakeIntelApi implements IntelApi {
  FakeIntelApi({List<IntelAlert>? alerts}) : alerts = alerts ?? _defaultAlerts();

  List<IntelAlert> alerts;
  bool offline = false;
  IntelException? error;
  final List<String> marked = [];
  final List<Map<String, Object?>> alertCalls = [];
  final DateTime cachedAt = DateTime.utc(2026, 10, 10, 12, 30);

  static List<IntelAlert> _defaultAlerts() => [
        IntelAlert(
          id: 'a1',
          title: 'Nuevo registro SAG: Draxxin',
          priority: 'critical',
          competitor: 'ZOETIS CHILE S.A.',
          subtype: 'NEWSKU',
          source: 'SAG',
          createdAt: DateTime.now().toUtc().subtract(const Duration(minutes: 5)),
          data: const {'Registro': '1001', 'Clasificación': 'ANTIMICROBIANOS'},
        ),
        IntelAlert(
          id: 'a2',
          title: 'Nueva publicación Drag Pharma: Lanzamiento',
          priority: 'medium',
          competitor: 'Drag Pharma',
          subtype: 'NOTICIA',
          source: 'Web competidor',
          createdAt: DateTime.now().toUtc().subtract(const Duration(hours: 3)),
        ),
      ];

  @override
  Future<IntelResult<IntelAlertsPage>> fetchAlerts({
    String? priority,
    String? type,
    String? competitor,
    int offset = 0,
    int limit = 50,
  }) async {
    alertCalls.add({'priority': priority, 'type': type, 'competitor': competitor, 'offset': offset});
    if (error != null) throw error!;
    var filtered = alerts.where((a) => priority == null || a.priority == priority).toList();
    if ((competitor ?? '').trim().isNotEmpty) {
      filtered = filtered.where((a) => (a.competitor ?? '').toLowerCase().contains(competitor!.toLowerCase())).toList();
    }
    final page = filtered.skip(offset).take(limit).toList();
    return IntelResult(
      IntelAlertsPage(alerts: page, total: filtered.length, hasMore: offset + page.length < filtered.length),
      fromCache: offline,
      cachedAt: offline ? cachedAt : null,
    );
  }

  @override
  Future<void> markRead(String alertId) async => marked.add(alertId);

  @override
  Future<int> unreadCount() async => alerts.where((a) => !a.leida).length;

  @override
  Future<IntelResult<List<ProductSummary>>> searchProducts(String query) async {
    if (error != null) throw error!;
    final all = [
      const ProductSummary(
          registro: '1001', nombreComercial: 'Draxxin', principioActivo: 'TULATROMICINA', titular: 'ZOETIS CHILE S.A.'),
    ];
    return IntelResult(all.where((p) => p.matches(query)).toList());
  }

  @override
  Future<IntelResult<ProductSheet>> fetchSheet(String registro) async => IntelResult(
        ProductSheet(
          summary: const ProductSummary(
              registro: '1001', nombreComercial: 'Draxxin', principioActivo: 'TULATROMICINA', titular: 'ZOETIS CHILE S.A.'),
          registroSag: const {'Especies': 'BOVINO'},
          alertas: const [
            {'id': 'sag_newsku_1001', 'tipo': 'NEWSKU', 'titulo': 'Nuevo registro SAG: Draxxin'}
          ],
          fuentes: const [
            {'dato': 'registro_sag', 'origen': 'SAG (Enci-Intel)', 'fecha': '2026-10-01T10:00:00+00:00'}
          ],
        ),
      );
}

/// Chat de relleno: estas pruebas son de alertas y productos.
class NoopChatApi implements CompetenciaChatApi {
  @override
  Stream<ChatEvent> ask(String question, {String? conversationId}) => const Stream.empty();
  @override
  Future<ChatData<List<ConversationSummary>>> conversations() async => const ChatData([]);
  @override
  Future<ChatData<List<ChatMessage>>> loadConversation(String id) async => const ChatData([]);
  @override
  Future<void> deleteConversation(String id) async {}
  @override
  Future<void> sendFeedback(String conversationId, int index, String? value) async {}
  @override
  Future<UsageInfo> usage() async => const UsageInfo(usadas: 0, limite: 50);
}

Future<void> pumpPage(WidgetTester tester, FakeIntelApi api, {VoidCallback? onUnreadChanged}) async {
  tester.view.physicalSize = const Size(800, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: InteligenciaPage(api: api, chatApi: NoopChatApi(), onUnreadChanged: onUnreadChanged)),
  ));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('muestra el feed con prioridad, competidor y alertas sin leer', (tester) async {
    await pumpPage(tester, FakeIntelApi());

    expect(find.text('Nuevo registro SAG: Draxxin'), findsOneWidget);
    expect(find.text('Nueva publicación Drag Pharma: Lanzamiento'), findsOneWidget);
    expect(find.text('ZOETIS CHILE S.A.'), findsOneWidget);
    expect(find.text('Crítica'), findsWidgets);
    expect(find.byKey(const Key('unread-dot-a1')), findsOneWidget);
    expect(find.byKey(const Key('intel-offline-banner')), findsNothing);
  });

  testWidgets('filtrar por prioridad vuelve a pedir el feed con ese filtro', (tester) async {
    final api = FakeIntelApi();
    await pumpPage(tester, api);

    await tester.tap(find.byKey(const Key('priority-chip-critical')));
    await tester.pumpAndSettle();

    expect(api.alertCalls.last['priority'], 'critical');
    expect(find.text('Nuevo registro SAG: Draxxin'), findsOneWidget);
    expect(find.text('Nueva publicación Drag Pharma: Lanzamiento'), findsNothing);
  });

  testWidgets('filtrar por competidor al confirmar el texto', (tester) async {
    final api = FakeIntelApi();
    await pumpPage(tester, api);

    await tester.enterText(find.byKey(const Key('competitor-field')), 'drag');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();

    expect(api.alertCalls.last['competitor'], 'drag');
    expect(find.text('Nuevo registro SAG: Draxxin'), findsNothing);
    expect(find.text('Nueva publicación Drag Pharma: Lanzamiento'), findsOneWidget);
  });

  testWidgets('abrir una alerta muestra el detalle, la marca como leida y avisa al contador', (tester) async {
    final api = FakeIntelApi();
    var notified = 0;
    await pumpPage(tester, api, onUnreadChanged: () => notified++);

    await tester.tap(find.byKey(const Key('intel-alert-a1')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('intel-alert-detail')), findsOneWidget);
    expect(find.text('Datos de origen'), findsOneWidget);
    expect(find.text('ANTIMICROBIANOS'), findsOneWidget);
    expect(api.marked, ['a1']);
    expect(notified, 1);
  });

  testWidgets('sin conexion muestra el aviso con la fecha de los datos guardados', (tester) async {
    final api = FakeIntelApi()..offline = true;
    await pumpPage(tester, api);

    expect(find.byKey(const Key('intel-offline-banner')), findsOneWidget);
    expect(find.textContaining('Sin conexión · datos del'), findsOneWidget);
    expect(find.text('Nuevo registro SAG: Draxxin'), findsOneWidget);
  });

  testWidgets('sin acceso a Inteligencia no ofrece reintentar', (tester) async {
    final api = FakeIntelApi()..error = const IntelException(IntelErrorKind.noAccess, 'Tu cuenta no tiene acceso a Inteligencia.');
    await pumpPage(tester, api);

    expect(find.text('Tu cuenta no tiene acceso a Inteligencia.'), findsOneWidget);
    expect(find.text('Reintentar'), findsNothing);
  });

  testWidgets('con Intel caido y sin copia local muestra un mensaje claro y permite reintentar', (tester) async {
    final api = FakeIntelApi()
      ..error = const IntelException(IntelErrorKind.unavailable, 'Enci-Intel no está disponible por ahora.');
    await pumpPage(tester, api);

    expect(find.textContaining('Enci-Intel no está disponible'), findsOneWidget);

    api.error = null;
    await tester.tap(find.text('Reintentar'));
    await tester.pumpAndSettle();

    expect(find.text('Nuevo registro SAG: Draxxin'), findsOneWidget);
  });

  testWidgets('el scroll al final carga la pagina siguiente', (tester) async {
    final many = [
      for (var i = 0; i < 60; i++)
        IntelAlert(id: 'b$i', title: 'Alerta $i', priority: 'low', createdAt: DateTime.now().toUtc()),
    ];
    final api = FakeIntelApi(alerts: many);
    await pumpPage(tester, api);
    expect(api.alertCalls.length, 1);

    await tester.drag(find.byType(ListView).first, const Offset(0, -6000));
    await tester.pumpAndSettle();

    expect(api.alertCalls.any((c) => c['offset'] == 50), isTrue);
  });

  testWidgets('buscar un producto y abrir su ficha', (tester) async {
    await pumpPage(tester, FakeIntelApi());

    await tester.tap(find.text('Productos'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('product-search-field')), 'tulatro');
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('product-1001')), findsOneWidget);

    await tester.tap(find.byKey(const Key('product-1001')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('intel-product-sheet')), findsOneWidget);
    expect(find.text('Sin producto equivalente registrado.'), findsOneWidget);
    expect(find.textContaining('Aún no hay precios'), findsOneWidget);
    expect(find.textContaining('SAG (Enci-Intel)'), findsOneWidget);
    expect(find.text('BOVINO'), findsOneWidget);
  });

  testWidgets('una busqueda de menos de 2 letras no consulta al servicio', (tester) async {
    await pumpPage(tester, FakeIntelApi());

    await tester.tap(find.text('Productos'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('product-search-field')), 'a');
    await tester.pump(const Duration(milliseconds: 600));

    expect(find.text('Busca un producto o competidor del registro SAG.'), findsOneWidget);
  });
}
