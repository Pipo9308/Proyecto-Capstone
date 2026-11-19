import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/chat_models.dart';

/// Copia local del historial del chat para poder leerlo sin conexion (RF-08.13).
/// Guarda la lista de conversaciones y las ultimas conversaciones abiertas.
class ChatCache {
  static const _kList = 'chat_conversations_v1';
  static const _kThreads = 'chat_threads_v1';
  static const maxThreads = 10;

  Future<void> saveConversations(List<ConversationSummary> items) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kList, jsonEncode(items.map((c) => c.toJson()).toList()));
    } catch (_) {}
  }

  Future<List<ConversationSummary>?> loadConversations() async {
    try {
      final raw = (await SharedPreferences.getInstance()).getString(_kList);
      if (raw == null) return null;
      return (jsonDecode(raw) as List)
          .map((e) => ConversationSummary.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList();
    } catch (_) {
      return null;
    }
  }

  Future<void> saveThread(String id, List<ChatMessage> messages) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final threads = await _readThreads(prefs);
      threads.remove(id);
      threads[id] = messages.map((m) => m.toJson()).toList();
      // Un Map de Dart conserva el orden de insercion: se descartan las mas antiguas.
      while (threads.length > maxThreads) {
        threads.remove(threads.keys.first);
      }
      await prefs.setString(_kThreads, jsonEncode(threads));
    } catch (_) {}
  }

  Future<List<ChatMessage>?> loadThread(String id) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final stored = (await _readThreads(prefs))[id];
      if (stored == null) return null;
      return [
        for (var i = 0; i < (stored as List).length; i++)
          ChatMessage.fromStored(Map<String, dynamic>.from(stored[i] as Map), i),
      ];
    } catch (_) {
      return null;
    }
  }

  Future<void> removeThread(String id) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final threads = await _readThreads(prefs)..remove(id);
      await prefs.setString(_kThreads, jsonEncode(threads));
      final list = await loadConversations();
      if (list != null) await saveConversations(list.where((c) => c.id != id).toList());
    } catch (_) {}
  }

  Future<void> clear() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_kList);
      await prefs.remove(_kThreads);
    } catch (_) {}
  }

  Future<Map<String, dynamic>> _readThreads(SharedPreferences prefs) async {
    final raw = prefs.getString(_kThreads);
    if (raw == null) return {};
    return Map<String, dynamic>.from(jsonDecode(raw) as Map);
  }
}
