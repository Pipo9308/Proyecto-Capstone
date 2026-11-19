// Modelos de la integracion con Enci-Intel (alertas de competencia y fichas SAG).

/// Las fechas de Intel son UTC; si llegan sin zona (datos antiguos en cache) se
/// asumen UTC en vez de interpretarlas como hora local.
DateTime? parseUtc(Object? value) {
  if (value == null) return null;
  final text = value.toString();
  if (text.isEmpty) return null;
  final hasZone = text.endsWith('Z') || RegExp(r'[+-]\d{2}:?\d{2}$').hasMatch(text);
  return DateTime.tryParse(hasZone ? text : '${text}Z');
}

String priorityLabel(String priority) {
  switch (priority.toLowerCase()) {
    case 'critical':
      return 'Crítica';
    case 'high':
      return 'Alta';
    case 'medium':
      return 'Media';
    default:
      return 'Baja';
  }
}

String alertTypeLabel(String? subtype) {
  switch ((subtype ?? '').toUpperCase()) {
    case 'NEWSKU':
      return 'Nuevo registro';
    case 'CANCELACION':
      return 'Cancelación';
    case 'NOTICIA':
      return 'Noticia';
    default:
      return subtype ?? 'Alerta';
  }
}

/// "hace 5 min", "hace 3 h", "hace 2 d" o la fecha si pasaron mas de 30 dias.
String timeAgo(DateTime? moment, {DateTime? now}) {
  if (moment == null) return '';
  final reference = (now ?? DateTime.now()).toUtc();
  final diff = reference.difference(moment.toUtc());
  if (diff.inMinutes < 1) return 'ahora';
  if (diff.inMinutes < 60) return 'hace ${diff.inMinutes} min';
  if (diff.inHours < 24) return 'hace ${diff.inHours} h';
  if (diff.inDays < 30) return 'hace ${diff.inDays} d';
  return formatDate(moment);
}

String formatDate(DateTime moment) {
  final local = moment.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(local.day)}/${two(local.month)}/${local.year}';
}

/// "dd/mm a las hh:mm", usado en el aviso de datos sin conexion.
String formatDateTime(DateTime moment) {
  final local = moment.toLocal();
  String two(int n) => n.toString().padLeft(2, '0');
  return '${two(local.day)}/${two(local.month)} a las ${two(local.hour)}:${two(local.minute)}';
}

class IntelAlert {
  const IntelAlert({
    required this.id,
    required this.title,
    required this.priority,
    this.competitor,
    this.type,
    this.subtype,
    this.source,
    this.description,
    this.createdAt,
    this.data = const {},
    this.leida = false,
  });

  final String id;
  final String title;
  final String priority;
  final String? competitor;
  final String? type;
  final String? subtype;
  final String? source;
  final String? description;
  final DateTime? createdAt;
  final Map<String, dynamic> data;
  final bool leida;

  factory IntelAlert.fromJson(Map<String, dynamic> json) {
    final rawData = json['data'];
    return IntelAlert(
      id: json['id'].toString(),
      title: (json['title'] ?? 'Alerta').toString(),
      priority: (json['priority'] ?? 'low').toString().toLowerCase(),
      competitor: json['competitor']?.toString(),
      type: json['type']?.toString(),
      subtype: json['subtype']?.toString(),
      source: json['source']?.toString(),
      description: (json['description'] ?? json['body'])?.toString(),
      createdAt: parseUtc(json['created_at']),
      data: rawData is Map ? Map<String, dynamic>.from(rawData) : const {},
      leida: json['leida'] == true,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'priority': priority,
        'competitor': competitor,
        'type': type,
        'subtype': subtype,
        'source': source,
        'description': description,
        'created_at': createdAt?.toUtc().toIso8601String(),
        'data': data,
        'leida': leida,
      };

  IntelAlert copyWith({bool? leida}) => IntelAlert(
        id: id,
        title: title,
        priority: priority,
        competitor: competitor,
        type: type,
        subtype: subtype,
        source: source,
        description: description,
        createdAt: createdAt,
        data: data,
        leida: leida ?? this.leida,
      );
}

class IntelAlertsPage {
  const IntelAlertsPage({required this.alerts, required this.total, required this.hasMore});

  final List<IntelAlert> alerts;
  final int total;
  final bool hasMore;

  factory IntelAlertsPage.fromJson(Map<String, dynamic> json) {
    final items = (json['data'] as List? ?? const [])
        .map((e) => IntelAlert.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    return IntelAlertsPage(
      alerts: items,
      total: (json['total'] as num?)?.toInt() ?? items.length,
      hasMore: json['has_more'] == true,
    );
  }
}

class ProductSummary {
  const ProductSummary({
    required this.registro,
    this.nombreComercial,
    this.principioActivo,
    this.titular,
    this.fabricante,
    this.clasificacion,
    this.estado,
  });

  final String registro;
  final String? nombreComercial;
  final String? principioActivo;
  final String? titular;
  final String? fabricante;
  final String? clasificacion;
  final String? estado;

  factory ProductSummary.fromJson(Map<String, dynamic> json) => ProductSummary(
        registro: json['registro'].toString(),
        nombreComercial: json['nombre_comercial']?.toString(),
        principioActivo: json['principio_activo']?.toString(),
        titular: json['titular']?.toString(),
        fabricante: json['fabricante']?.toString(),
        clasificacion: json['clasificacion']?.toString(),
        estado: json['estado']?.toString(),
      );

  Map<String, dynamic> toJson() => {
        'registro': registro,
        'nombre_comercial': nombreComercial,
        'principio_activo': principioActivo,
        'titular': titular,
        'fabricante': fabricante,
        'clasificacion': clasificacion,
        'estado': estado,
      };

  /// Coincidencia simple usada para buscar entre las fichas guardadas sin conexion.
  bool matches(String query) {
    final needle = query.trim().toLowerCase();
    if (needle.isEmpty) return true;
    return [registro, nombreComercial, principioActivo, titular, fabricante]
        .whereType<String>()
        .any((value) => value.toLowerCase().contains(needle));
  }
}

class ProductSheet {
  const ProductSheet({
    required this.summary,
    this.actualizado,
    this.registroSag = const {},
    this.alertas = const [],
    this.precios = const [],
    this.equivalenteEncipharm,
    this.fuentes = const [],
  });

  final ProductSummary summary;
  final DateTime? actualizado;
  final Map<String, dynamic> registroSag;
  final List<Map<String, dynamic>> alertas;
  final List<Map<String, dynamic>> precios;
  final Map<String, dynamic>? equivalenteEncipharm;
  final List<Map<String, dynamic>> fuentes;

  factory ProductSheet.fromJson(Map<String, dynamic> json) {
    List<Map<String, dynamic>> maps(Object? value) =>
        (value as List? ?? const []).map((e) => Map<String, dynamic>.from(e as Map)).toList();
    final equivalent = json['equivalente_encipharm'];
    return ProductSheet(
      summary: ProductSummary.fromJson(json),
      actualizado: parseUtc(json['actualizado']),
      registroSag: json['registro_sag'] is Map ? Map<String, dynamic>.from(json['registro_sag'] as Map) : const {},
      alertas: maps(json['alertas']),
      precios: maps(json['precios']),
      equivalenteEncipharm: equivalent is Map ? Map<String, dynamic>.from(equivalent) : null,
      fuentes: maps(json['fuentes']),
    );
  }

  Map<String, dynamic> toJson() => {
        ...summary.toJson(),
        'actualizado': actualizado?.toUtc().toIso8601String(),
        'registro_sag': registroSag,
        'alertas': alertas,
        'precios': precios,
        'equivalente_encipharm': equivalenteEncipharm,
        'fuentes': fuentes,
      };
}
