import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_vendedor/models/chat_models.dart';
import 'package:flutter_vendedor/services/chat_sse.dart';

String sse(List<Map<String, Object?>> events) => events.map((e) => 'data: ${jsonEncode(e)}\n\n').join();

Future<List<ChatEvent>> parse(Iterable<List<int>> chunks) => parseSse(Stream.fromIterable(chunks)).toList();

void main() {
  final sample = sse([
    {'tipo': 'estado', 'texto': 'Revisando datos de Enci-Intel…'},
    {
      'tipo': 'fuentes',
      'fuentes': [
        {'origen': 'enci-intel', 'titulo': 'Nuevo registro SAG: Draxxin', 'fecha': '2026-10-05T10:00:00+00:00', 'url': null},
        {'origen': 'web', 'titulo': 'Diario', 'fecha': null, 'url': 'https://diario.cl/z'},
      ],
    },
    {'tipo': 'texto', 'texto': 'Zoetis registró '},
    {'tipo': 'texto', 'texto': 'Draxxin.'},
    {'tipo': 'fin', 'conversacion_id': 'c-1', 'mensaje_indice': 1, 'funciones': ['buscar_alertas']},
  ]);

  test('lee todos los eventos en orden', () async {
    final events = await parse([utf8.encode(sample)]);

    expect(events.map((e) => e.tipo), ['estado', 'fuentes', 'texto', 'texto', 'fin']);
    expect(events[0].texto, 'Revisando datos de Enci-Intel…');
    expect(events[1].fuentes.length, 2);
    expect(events[1].fuentes[1].isWeb, isTrue);
    expect(events[1].fuentes[0].originLabel, 'Enci-Intel');
    expect(events.last.conversacionId, 'c-1');
    expect(events.last.mensajeIndice, 1);
  });

  test('un evento partido en cualquier byte se reconstruye igual', () async {
    final bytes = utf8.encode(sample);
    for (final size in [1, 2, 3, 7, 50]) {
      final chunks = [for (var i = 0; i < bytes.length; i += size) bytes.sublist(i, i + size > bytes.length ? bytes.length : i + size)];

      final events = await parse(chunks);

      expect(events.map((e) => e.tipo), ['estado', 'fuentes', 'texto', 'texto', 'fin'], reason: 'trozos de $size bytes');
      expect(events[2].texto! + events[3].texto!, 'Zoetis registró Draxxin.');
    }
  });

  test('los caracteres con tilde no se rompen aunque el UTF-8 llegue partido', () async {
    final bytes = utf8.encode(sse([
      {'tipo': 'texto', 'texto': 'Cancelación del registro ñandú'}
    ]));

    final events = await parse([for (final b in bytes) [b]]);

    expect(events.single.texto, 'Cancelación del registro ñandú');
  });

  test('acepta saltos de linea CRLF', () async {
    final crlf = sample.replaceAll('\n', '\r\n');

    expect((await parse([utf8.encode(crlf)])).length, 5);
  });

  test('un evento mal formado se ignora sin cortar el resto', () async {
    final broken = 'data: {no es json\n\n${sse([
      {'tipo': 'fin', 'conversacion_id': 'c-9'}
    ])}';

    final events = await parse([utf8.encode(broken)]);

    expect(events.map((e) => e.tipo), ['fin']);
  });

  test('ignora comentarios y lineas que no son data', () async {
    final noisy = ': keep-alive\n\nevent: x\ndata: {"tipo":"fin"}\n\n';

    expect((await parse([utf8.encode(noisy)])).single.tipo, 'fin');
  });

  test('un error del backend llega como evento con su codigo y estado', () async {
    final events = await parse([
      utf8.encode(sse([
        {'tipo': 'error', 'estado': 503, 'codigo': 'COMPETENCIA_LLM_TIMEOUT', 'mensaje': 'tardó demasiado'}
      ]))
    ]);

    expect(events.single.estado, 503);
    expect(events.single.codigo, 'COMPETENCIA_LLM_TIMEOUT');
    expect(events.single.mensaje, 'tardó demasiado');
  });
}
