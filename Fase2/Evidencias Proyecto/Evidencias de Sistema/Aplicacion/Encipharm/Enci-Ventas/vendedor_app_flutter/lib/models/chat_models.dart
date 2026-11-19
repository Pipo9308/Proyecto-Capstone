// Modelos del chat de competencia (RQ-08).

/// Fuente de una respuesta: `enci-intel` (dato interno) o `web` (internet).
class ChatSource {
  const ChatSource({required this.origen, required this.titulo, this.fecha, this.url});

  final String origen;
  final String titulo;
  final String? fecha;
  final String? url;

  bool get isWeb => origen == 'web';
  String get originLabel => isWeb ? 'Internet' : 'Enci-Intel';

  factory ChatSource.fromJson(Map<String, dynamic> json) => ChatSource(
        origen: (json['origen'] ?? 'enci-intel').toString(),
        titulo: (json['titulo'] ?? 'Sin título').toString(),
        fecha: json['fecha']?.toString(),
        url: json['url']?.toString(),
      );

  Map<String, dynamic> toJson() => {'origen': origen, 'titulo': titulo, 'fecha': fecha, 'url': url};
}

List<ChatSource> _sources(Object? value) => (value as List? ?? const [])
    .map((e) => ChatSource.fromJson(Map<String, dynamic>.from(e as Map)))
    .toList();

class ChatMessage {
  const ChatMessage({
    required this.role,
    required this.text,
    this.sources = const [],
    this.feedback,
    this.index,
    this.isError = false,
  });

  /// `user` o `assistant`.
  final String role;
  final String text;
  final List<ChatSource> sources;

  /// `up`, `down` o null.
  final String? feedback;

  /// Posicion en la conversacion guardada (solo las respuestas confirmadas la tienen).
  final int? index;
  final bool isError;

  bool get isUser => role == 'user';

  ChatMessage copyWith({String? text, List<ChatSource>? sources, String? feedback, bool clearFeedback = false, int? index}) =>
      ChatMessage(
        role: role,
        text: text ?? this.text,
        sources: sources ?? this.sources,
        feedback: clearFeedback ? null : (feedback ?? this.feedback),
        index: index ?? this.index,
        isError: isError,
      );

  factory ChatMessage.fromStored(Map<String, dynamic> json, int position) => ChatMessage(
        role: (json['rol'] ?? 'assistant').toString(),
        text: (json['contenido'] ?? '').toString(),
        sources: _sources(json['fuentes']),
        feedback: json['feedback']?.toString(),
        index: position,
      );

  Map<String, dynamic> toJson() => {
        'rol': role,
        'contenido': text,
        'fuentes': sources.map((s) => s.toJson()).toList(),
        'feedback': feedback,
      };
}

class ConversationSummary {
  const ConversationSummary({required this.id, required this.titulo, this.mensajes = 0});

  final String id;
  final String titulo;
  final int mensajes;

  factory ConversationSummary.fromJson(Map<String, dynamic> json) => ConversationSummary(
        id: json['id'].toString(),
        titulo: (json['titulo'] ?? 'Conversación').toString(),
        mensajes: (json['mensajes'] as num?)?.toInt() ?? 0,
      );

  Map<String, dynamic> toJson() => {'id': id, 'titulo': titulo, 'mensajes': mensajes};
}

class UsageInfo {
  const UsageInfo({required this.usadas, required this.limite});

  final int usadas;
  final int limite;
  int get restantes => (limite - usadas) < 0 ? 0 : limite - usadas;

  factory UsageInfo.fromJson(Map<String, dynamic> json) => UsageInfo(
        usadas: (json['usadas'] as num?)?.toInt() ?? 0,
        limite: (json['limite'] as num?)?.toInt() ?? 0,
      );
}

/// Evento del stream de respuesta: estado, fuentes, texto, fin o error.
class ChatEvent {
  const ChatEvent({
    required this.tipo,
    this.texto,
    this.fuentes = const [],
    this.conversacionId,
    this.mensajeIndice,
    this.codigo,
    this.mensaje,
    this.estado,
  });

  final String tipo;
  final String? texto;
  final List<ChatSource> fuentes;
  final String? conversacionId;
  final int? mensajeIndice;
  final String? codigo;
  final String? mensaje;
  final int? estado;

  factory ChatEvent.fromJson(Map<String, dynamic> json) => ChatEvent(
        tipo: (json['tipo'] ?? '').toString(),
        texto: json['texto']?.toString(),
        fuentes: _sources(json['fuentes']),
        conversacionId: json['conversacion_id']?.toString(),
        mensajeIndice: (json['mensaje_indice'] as num?)?.toInt(),
        codigo: json['codigo']?.toString(),
        mensaje: json['mensaje']?.toString(),
        estado: (json['estado'] as num?)?.toInt(),
      );
}
