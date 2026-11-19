import 'dart:convert';

import '../models/chat_models.dart';

/// Convierte el cuerpo `text/event-stream` del backend en eventos del chat.
///
/// Cada evento llega como `data: {json}` seguido de una linea en blanco. Los bloques
/// pueden venir partidos en cualquier punto (incluso dentro de un caracter UTF-8),
/// asi que se acumula hasta tener el bloque completo.
Stream<ChatEvent> parseSse(Stream<List<int>> bytes) async* {
  var buffer = '';
  await for (final chunk in utf8.decoder.bind(bytes)) {
    buffer = (buffer + chunk).replaceAll('\r\n', '\n');
    while (true) {
      final end = buffer.indexOf('\n\n');
      if (end < 0) break;
      final block = buffer.substring(0, end);
      buffer = buffer.substring(end + 2);
      for (final line in block.split('\n')) {
        if (!line.startsWith('data:')) continue;
        final payload = line.substring(5).trim();
        if (payload.isEmpty) continue;
        try {
          yield ChatEvent.fromJson(Map<String, dynamic>.from(jsonDecode(payload) as Map));
        } catch (_) {
          // Un evento mal formado no debe cortar la respuesta completa.
        }
      }
    }
  }
}
