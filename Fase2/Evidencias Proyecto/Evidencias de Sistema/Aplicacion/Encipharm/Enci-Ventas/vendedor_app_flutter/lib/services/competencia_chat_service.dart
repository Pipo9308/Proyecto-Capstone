import 'dart:convert';

import 'package:dio/dio.dart';

import '../models/chat_models.dart';
import 'api_service.dart';
import 'chat_cache.dart';
import 'chat_sse.dart';

enum ChatErrorKind { noAccess, quota, offline, other }

class ChatException implements Exception {
  const ChatException(this.kind, this.message);
  final ChatErrorKind kind;
  final String message;

  @override
  String toString() => message;
}

/// Resultado con indicador de que viene de la copia local (sin conexion).
class ChatData<T> {
  const ChatData(this.data, {this.fromCache = false});
  final T data;
  final bool fromCache;
}

abstract class CompetenciaChatApi {
  Stream<ChatEvent> ask(String question, {String? conversationId});
  Future<ChatData<List<ConversationSummary>>> conversations();
  Future<ChatData<List<ChatMessage>>> loadConversation(String id);
  Future<void> deleteConversation(String id);
  Future<void> sendFeedback(String conversationId, int index, String? value);
  Future<UsageInfo> usage();
}

/// Habla con `/inteligencia/competencia-chat/*` del backend de Ventas.
class CompetenciaChatService implements CompetenciaChatApi {
  CompetenciaChatService({ChatCache? cache}) : _cache = cache ?? ChatCache();

  final ChatCache _cache;
  static const _base = '/inteligencia/competencia-chat';

  static bool _isOffline(DioException e) =>
      e.type == DioExceptionType.connectionError ||
      e.type == DioExceptionType.connectionTimeout ||
      e.type == DioExceptionType.sendTimeout ||
      e.type == DioExceptionType.receiveTimeout ||
      e.response?.statusCode == 502 ||
      e.response?.statusCode == 503 ||
      e.response?.statusCode == 504;

  /// Lee el mensaje de error del backend aunque la respuesta venga como stream.
  static Future<String?> _backendMessage(Response<dynamic>? response) async {
    try {
      var data = response?.data;
      if (data is ResponseBody) {
        final bytes = await data.stream.expand((b) => b).toList();
        data = jsonDecode(utf8.decode(bytes));
      }
      if (data is Map) return (data['error'] ?? data['detail'])?.toString();
    } catch (_) {}
    return null;
  }

  static Future<ChatException> _translate(Object error) async {
    if (error is DioException) {
      if (error.message == 'SIN_ACCESO' || error.error == 'SIN_ACCESO') {
        return const ChatException(ChatErrorKind.noAccess, 'Tu cuenta no tiene acceso a Inteligencia.');
      }
      if (error.response?.statusCode == 429) {
        final message = await _backendMessage(error.response);
        return ChatException(ChatErrorKind.quota, message ?? 'Alcanzaste el tope diario de preguntas.');
      }
      if (_isOffline(error)) {
        return const ChatException(
          ChatErrorKind.offline,
          'Necesitas conexión a internet para consultar. Puedes leer tus conversaciones guardadas.',
        );
      }
    }
    return const ChatException(ChatErrorKind.other, 'No se pudo completar la consulta. Intenta de nuevo.');
  }

  @override
  Stream<ChatEvent> ask(String question, {String? conversationId}) async* {
    final dio = await ApiService.authClient();
    Response<ResponseBody> response;
    try {
      response = await dio.post<ResponseBody>(
        '$_base/stream',
        data: {'pregunta': question, 'conversacion_id': ?conversationId},
        options: Options(responseType: ResponseType.stream, receiveTimeout: const Duration(seconds: 90)),
      );
    } catch (e) {
      throw await _translate(e);
    }
    yield* parseSse(response.data!.stream);
  }

  @override
  Future<ChatData<List<ConversationSummary>>> conversations() async {
    try {
      final dio = await ApiService.authClient();
      final res = await dio.get('$_base/conversaciones');
      final items = (res.data as List)
          .map((e) => ConversationSummary.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();
      await _cache.saveConversations(items);
      return ChatData(items);
    } catch (e) {
      final translated = await _translate(e);
      final cached = translated.kind == ChatErrorKind.offline ? await _cache.loadConversations() : null;
      if (cached != null) return ChatData(cached, fromCache: true);
      throw translated;
    }
  }

  @override
  Future<ChatData<List<ChatMessage>>> loadConversation(String id) async {
    try {
      final dio = await ApiService.authClient();
      final res = await dio.get('$_base/conversaciones/$id');
      final raw = (res.data['mensajes'] as List? ?? const []);
      final messages = [
        for (var i = 0; i < raw.length; i++) ChatMessage.fromStored(Map<String, dynamic>.from(raw[i] as Map), i),
      ];
      await _cache.saveThread(id, messages);
      return ChatData(messages);
    } catch (e) {
      final translated = await _translate(e);
      final cached = translated.kind == ChatErrorKind.offline ? await _cache.loadThread(id) : null;
      if (cached != null) return ChatData(cached, fromCache: true);
      throw translated;
    }
  }

  @override
  Future<void> deleteConversation(String id) async {
    try {
      final dio = await ApiService.authClient();
      await dio.delete('$_base/conversaciones/$id');
      await _cache.removeThread(id);
    } catch (e) {
      throw await _translate(e);
    }
  }

  @override
  Future<void> sendFeedback(String conversationId, int index, String? value) async {
    try {
      final dio = await ApiService.authClient();
      await dio.patch('$_base/conversaciones/$conversationId/mensajes/$index/feedback', data: {'valor': value});
    } catch (e) {
      throw await _translate(e);
    }
  }

  @override
  Future<UsageInfo> usage() async {
    try {
      final dio = await ApiService.authClient();
      final res = await dio.get('$_base/uso');
      return UsageInfo.fromJson(Map<String, dynamic>.from(res.data as Map));
    } catch (e) {
      throw await _translate(e);
    }
  }
}
