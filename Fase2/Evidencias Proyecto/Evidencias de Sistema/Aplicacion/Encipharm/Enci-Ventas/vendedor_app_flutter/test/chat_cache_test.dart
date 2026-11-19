import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_vendedor/models/chat_models.dart';
import 'package:flutter_vendedor/services/chat_cache.dart';
import 'package:shared_preferences/shared_preferences.dart';

List<ChatMessage> thread(String question) => [
      ChatMessage(role: 'user', text: question),
      ChatMessage(
        role: 'assistant',
        text: 'Respuesta a $question',
        sources: const [ChatSource(origen: 'web', titulo: 'Diario', url: 'https://diario.cl')],
        feedback: 'up',
      ),
    ];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late ChatCache cache;

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    cache = ChatCache();
  });

  test('sin datos no hay historial guardado', () async {
    expect(await cache.loadConversations(), isNull);
    expect(await cache.loadThread('c-1'), isNull);
  });

  test('guarda y recupera la lista de conversaciones', () async {
    await cache.saveConversations(const [ConversationSummary(id: 'c-1', titulo: 'Zoetis', mensajes: 4)]);

    final loaded = (await cache.loadConversations())!;

    expect(loaded.single.id, 'c-1');
    expect(loaded.single.titulo, 'Zoetis');
    expect(loaded.single.mensajes, 4);
  });

  test('una conversacion guardada conserva textos, fuentes, feedback y posicion', () async {
    await cache.saveThread('c-1', thread('¿Qué hizo Zoetis?'));

    final loaded = (await cache.loadThread('c-1'))!;

    expect(loaded.length, 2);
    expect(loaded[0].isUser, isTrue);
    expect(loaded[1].text, 'Respuesta a ¿Qué hizo Zoetis?');
    expect(loaded[1].sources.single.isWeb, isTrue);
    expect(loaded[1].feedback, 'up');
    expect(loaded[1].index, 1);
  });

  test('mantiene solo las 10 conversaciones mas recientes', () async {
    for (var i = 0; i < 12; i++) {
      await cache.saveThread('c-$i', thread('p$i'));
    }

    expect(await cache.loadThread('c-0'), isNull);
    expect(await cache.loadThread('c-1'), isNull);
    expect(await cache.loadThread('c-2'), isNotNull);
    expect(await cache.loadThread('c-11'), isNotNull);
  });

  test('volver a guardar una conversacion la marca como la mas reciente', () async {
    for (var i = 0; i < 10; i++) {
      await cache.saveThread('c-$i', thread('p$i'));
    }
    await cache.saveThread('c-0', thread('actualizada'));
    await cache.saveThread('c-nueva', thread('otra'));

    expect(await cache.loadThread('c-0'), isNotNull);
    expect(await cache.loadThread('c-1'), isNull);
  });

  test('eliminar una conversacion la quita del historial y de la lista', () async {
    await cache.saveConversations(const [
      ConversationSummary(id: 'c-1', titulo: 'A'),
      ConversationSummary(id: 'c-2', titulo: 'B'),
    ]);
    await cache.saveThread('c-1', thread('a'));

    await cache.removeThread('c-1');

    expect(await cache.loadThread('c-1'), isNull);
    expect((await cache.loadConversations())!.map((c) => c.id), ['c-2']);
  });

  test('clear borra todo (cambio de usuario en el dispositivo)', () async {
    await cache.saveConversations(const [ConversationSummary(id: 'c-1', titulo: 'A')]);
    await cache.saveThread('c-1', thread('a'));

    await cache.clear();

    expect(await cache.loadConversations(), isNull);
    expect(await cache.loadThread('c-1'), isNull);
  });
}
