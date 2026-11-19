import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_vendedor/models/chat_models.dart';
import 'package:flutter_vendedor/pages/competencia_chat_view.dart';
import 'package:flutter_vendedor/services/competencia_chat_service.dart';

class FakeChatApi implements CompetenciaChatApi {
  List<ChatEvent> script = [];
  ChatException? askError;
  final List<String> questions = [];
  final List<String?> conversationIds = [];
  final List<String> feedback = [];
  List<ConversationSummary> history = [
    const ConversationSummary(id: 'c-old', titulo: 'Draxxin de Zoetis', mensajes: 4),
  ];
  bool historyFromCache = false;
  UsageInfo usageInfo = const UsageInfo(usadas: 3, limite: 50);
  Completer<void>? gate;

  @override
  Stream<ChatEvent> ask(String question, {String? conversationId}) async* {
    questions.add(question);
    conversationIds.add(conversationId);
    if (askError != null) throw askError!;
    for (final event in script) {
      if (gate != null && event.tipo == 'texto') await gate!.future;
      yield event;
    }
  }

  @override
  Future<ChatData<List<ConversationSummary>>> conversations() async => ChatData(history, fromCache: historyFromCache);

  @override
  Future<ChatData<List<ChatMessage>>> loadConversation(String id) async => const ChatData([
        ChatMessage(role: 'user', text: 'pregunta vieja', index: 0),
        ChatMessage(role: 'assistant', text: 'respuesta vieja', index: 1),
      ]);

  @override
  Future<void> deleteConversation(String id) async => history = history.where((c) => c.id != id).toList();

  @override
  Future<void> sendFeedback(String conversationId, int index, String? value) async =>
      feedback.add('$conversationId:$index:$value');

  @override
  Future<UsageInfo> usage() async => usageInfo;
}

const intelSource = ChatSource(origen: 'enci-intel', titulo: 'Nuevo registro SAG: Draxxin', fecha: '2026-10-05T10:00:00+00:00');
const webSource = ChatSource(origen: 'web', titulo: 'Zoetis en el diario', fecha: null, url: 'https://diario.cl/zoetis');

List<ChatEvent> goodAnswer({String conversationId = 'c-new'}) => [
      const ChatEvent(tipo: 'estado', texto: 'Revisando datos de Enci-Intel…'),
      const ChatEvent(tipo: 'fuentes', fuentes: [intelSource, webSource]),
      const ChatEvent(tipo: 'texto', texto: 'Zoetis registró '),
      const ChatEvent(tipo: 'texto', texto: 'Draxxin.'),
      ChatEvent(tipo: 'fin', conversacionId: conversationId, mensajeIndice: 1),
    ];

Future<void> pump(WidgetTester tester, FakeChatApi api) async {
  tester.view.physicalSize = const Size(800, 1800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: CompetenciaChatView(api: api))));
  await tester.pumpAndSettle();
}

Future<void> send(WidgetTester tester, String text) async {
  await tester.enterText(find.byKey(const Key('chat-input')), text);
  await tester.tap(find.byKey(const Key('chat-send')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('al abrir muestra preguntas de ejemplo con competidores reales y el uso del dia', (tester) async {
    await pump(tester, FakeChatApi());

    expect(find.byKey(const Key('example-0')), findsOneWidget);
    expect(find.text('¿Qué registró Drag Pharma en el SAG este trimestre?'), findsOneWidget);
    expect(find.text('Preguntas hoy: 3/50'), findsOneWidget);
  });

  testWidgets('tocar un ejemplo lo envia como pregunta', (tester) async {
    final api = FakeChatApi()..script = goodAnswer();
    await pump(tester, api);

    await tester.tap(find.byKey(const Key('example-1')));
    await tester.pumpAndSettle();

    expect(api.questions, ['¿Cuáles son las últimas noticias de Zoetis Chile?']);
  });

  testWidgets('muestra la respuesta completa con sus fuentes y distingue Enci-Intel de Internet', (tester) async {
    final api = FakeChatApi()..script = goodAnswer();
    await pump(tester, api);

    await send(tester, '¿Qué registró Zoetis?');

    expect(find.text('¿Qué registró Zoetis?'), findsOneWidget);
    expect(find.text('Zoetis registró Draxxin.'), findsOneWidget);
    expect(find.text('Enci-Intel'), findsOneWidget);
    expect(find.text('Internet'), findsOneWidget);
    expect(find.textContaining('Nuevo registro SAG: Draxxin'), findsOneWidget);
    expect(find.text('https://diario.cl/zoetis'), findsOneWidget);
  });

  testWidgets('mientras responde muestra el estado y no deja enviar otra pregunta', (tester) async {
    final api = FakeChatApi()
      ..script = goodAnswer()
      ..gate = Completer<void>();
    await pump(tester, api);

    await tester.enterText(find.byKey(const Key('chat-input')), 'pregunta');
    await tester.tap(find.byKey(const Key('chat-send')));
    await tester.pump();
    await tester.pump();

    expect(find.text('Revisando datos de Enci-Intel…'), findsOneWidget);
    expect(tester.widget<IconButton>(find.byKey(const Key('chat-send'))).onPressed, isNull);

    api.gate!.complete();
    await tester.pumpAndSettle();

    expect(find.text('Zoetis registró Draxxin.'), findsOneWidget);
    expect(tester.widget<IconButton>(find.byKey(const Key('chat-send'))).onPressed, isNotNull);
  });

  testWidgets('la segunda pregunta continua la misma conversacion', (tester) async {
    final api = FakeChatApi()..script = goodAnswer(conversationId: 'c-77');
    await pump(tester, api);

    await send(tester, 'primera');
    await send(tester, 'segunda');

    expect(api.conversationIds, [null, 'c-77']);
  });

  testWidgets('el pulgar guarda el feedback y volver a tocarlo lo quita', (tester) async {
    final api = FakeChatApi()..script = goodAnswer(conversationId: 'c-5');
    await pump(tester, api);
    await send(tester, 'pregunta');

    await tester.tap(find.byKey(const Key('feedback-up-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('feedback-up-1')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('feedback-down-1')));
    await tester.pumpAndSettle();

    expect(api.feedback, ['c-5:1:up', 'c-5:1:null', 'c-5:1:down']);
  });

  testWidgets('al llegar al tope diario muestra el aviso del backend y conserva la pregunta', (tester) async {
    final api = FakeChatApi()
      ..askError = const ChatException(ChatErrorKind.quota, 'Alcanzaste el tope de 50 preguntas por dia.');
    await pump(tester, api);

    await send(tester, 'una mas');

    expect(find.byKey(const Key('chat-notice')), findsOneWidget);
    expect(find.text('Alcanzaste el tope de 50 preguntas por dia.'), findsOneWidget);
    expect(find.text('una mas'), findsOneWidget);
    expect(find.byKey(const Key('chat-bubble-1')), findsNothing); // la respuesta vacia se quita
  });

  testWidgets('sin conexion avisa que se necesita internet', (tester) async {
    final api = FakeChatApi()
      ..askError = const ChatException(ChatErrorKind.offline, 'Necesitas conexión a internet para consultar.');
    await pump(tester, api);

    await send(tester, 'hola');

    expect(find.textContaining('Necesitas conexión a internet'), findsOneWidget);
  });

  testWidgets('un error del modelo durante la respuesta se muestra como aviso', (tester) async {
    final api = FakeChatApi()
      ..script = const [ChatEvent(tipo: 'error', estado: 503, codigo: 'X', mensaje: 'El asistente no está disponible.')];
    await pump(tester, api);

    await send(tester, 'hola');

    expect(find.text('El asistente no está disponible.'), findsOneWidget);
  });

  testWidgets('el historial permite abrir una conversacion anterior', (tester) async {
    final api = FakeChatApi();
    await pump(tester, api);

    await tester.tap(find.byKey(const Key('chat-history')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('chat-history-sheet')), findsOneWidget);
    expect(find.text('Draxxin de Zoetis'), findsOneWidget);

    await tester.tap(find.byKey(const Key('history-c-old')));
    await tester.pumpAndSettle();

    expect(find.text('pregunta vieja'), findsOneWidget);
    expect(find.text('respuesta vieja'), findsOneWidget);
  });

  testWidgets('borrar una conversacion del historial la quita de la lista', (tester) async {
    final api = FakeChatApi();
    await pump(tester, api);
    await tester.tap(find.byKey(const Key('chat-history')));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('history-delete-c-old')));
    await tester.pumpAndSettle();

    expect(find.text('Draxxin de Zoetis'), findsNothing);
    expect(find.text('Aún no tienes conversaciones.'), findsOneWidget);
  });

  testWidgets('sin conexion el historial guardado se puede leer y se avisa', (tester) async {
    final api = FakeChatApi()..historyFromCache = true;
    await pump(tester, api);

    await tester.tap(find.byKey(const Key('chat-history')));
    await tester.pumpAndSettle();

    expect(find.text('Sin conexión · historial guardado'), findsOneWidget);
    expect(find.text('Draxxin de Zoetis'), findsOneWidget);
  });

  testWidgets('Nueva conversacion limpia el chat y vuelve a los ejemplos', (tester) async {
    final api = FakeChatApi()..script = goodAnswer();
    await pump(tester, api);
    await send(tester, 'algo');

    await tester.tap(find.byKey(const Key('chat-new')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('example-0')), findsOneWidget);
    expect(find.text('algo'), findsNothing);
  });
}
