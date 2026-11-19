import 'package:flutter/material.dart';

import '../models/chat_models.dart';
import '../models/intel_models.dart' show timeAgo, parseUtc;
import '../services/competencia_chat_service.dart';
import '../theme/app_colors.dart';

const exampleQuestions = <String>[
  '¿Qué registró Drag Pharma en el SAG este trimestre?',
  '¿Cuáles son las últimas noticias de Zoetis Chile?',
  '¿Qué alertas críticas hubo esta semana?',
];

/// Chat de competencia: responde con datos de Enci-Intel y, si el backend lo habilita,
/// con busqueda web. Cada respuesta muestra de donde sale cada dato.
class CompetenciaChatView extends StatefulWidget {
  const CompetenciaChatView({super.key, required this.api});
  final CompetenciaChatApi api;

  @override
  State<CompetenciaChatView> createState() => _CompetenciaChatViewState();
}

class _CompetenciaChatViewState extends State<CompetenciaChatView> with AutomaticKeepAliveClientMixin {
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scroll = ScrollController();
  List<ChatMessage> _messages = [];
  String? _conversationId;
  bool _sending = false;
  String? _status;
  ChatException? _notice;
  bool _fromCache = false;
  UsageInfo? _usage;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _loadUsage();
  }

  @override
  void dispose() {
    _controller.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _loadUsage() async {
    try {
      final usage = await widget.api.usage();
      if (mounted) setState(() => _usage = usage);
    } catch (_) {
      // El contador es informativo: sin red simplemente no se muestra.
    }
  }

  void _scrollDown() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  void _updateLast(ChatMessage Function(ChatMessage) change) {
    if (_messages.isEmpty) return;
    final updated = [..._messages];
    updated[updated.length - 1] = change(updated.last);
    setState(() => _messages = updated);
  }

  Future<void> _send(String question) async {
    final text = question.trim();
    if (text.isEmpty || _sending) return;
    _controller.clear();
    setState(() {
      _messages = [..._messages, ChatMessage(role: 'user', text: text), const ChatMessage(role: 'assistant', text: '')];
      _sending = true;
      _status = 'Pensando…';
      _notice = null;
      _fromCache = false;
    });
    _scrollDown();
    try {
      await for (final event in widget.api.ask(text, conversationId: _conversationId)) {
        if (!mounted) return;
        _apply(event);
      }
    } on ChatException catch (e) {
      _fail(e);
    } catch (_) {
      _fail(const ChatException(ChatErrorKind.other, 'No se pudo completar la consulta. Intenta de nuevo.'));
    } finally {
      if (mounted) {
        setState(() {
          _sending = false;
          _status = null;
        });
      }
    }
  }

  void _apply(ChatEvent event) {
    switch (event.tipo) {
      case 'estado':
        setState(() => _status = event.texto);
      case 'fuentes':
        _updateLast((m) => m.copyWith(sources: event.fuentes));
      case 'texto':
        _status = null;
        _updateLast((m) => m.copyWith(text: m.text + (event.texto ?? '')));
        _scrollDown();
      case 'fin':
        setState(() => _conversationId = event.conversacionId ?? _conversationId);
        _updateLast((m) => m.copyWith(index: event.mensajeIndice));
        _loadUsage();
      case 'error':
        final quota = event.estado == 429;
        _fail(ChatException(quota ? ChatErrorKind.quota : ChatErrorKind.other,
            event.mensaje ?? 'No se pudo generar la respuesta.'));
    }
  }

  void _fail(ChatException error) {
    if (!mounted) return;
    final updated = [..._messages];
    // La respuesta que no llego se quita; la pregunta se conserva para poder reintentarla.
    if (updated.isNotEmpty && !updated.last.isUser && updated.last.text.isEmpty) updated.removeLast();
    setState(() {
      _messages = updated;
      _notice = error;
    });
  }

  Future<void> _feedback(ChatMessage message, String value) async {
    final conversationId = _conversationId;
    final index = message.index;
    if (conversationId == null || index == null) return;
    final next = message.feedback == value ? null : value;
    ChatMessage apply(ChatMessage m, String? v) => identical(m, message)
        ? (v == null ? m.copyWith(clearFeedback: true) : m.copyWith(feedback: v))
        : m;
    setState(() => _messages = _messages.map((m) => apply(m, next)).toList());
    try {
      await widget.api.sendFeedback(conversationId, index, next);
    } catch (_) {
      if (!mounted) return;
      // No se pudo guardar: se deja como estaba.
      setState(() => _messages = _messages.map((m) => m.index == index ? message : m).toList());
    }
  }

  void _newConversation() {
    setState(() {
      _messages = [];
      _conversationId = null;
      _notice = null;
      _fromCache = false;
    });
  }

  Future<void> _openHistory() async {
    final picked = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.card,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => _HistorySheet(api: widget.api, currentId: _conversationId, onDeleted: (id) {
        if (id == _conversationId) _newConversation();
      }),
    );
    if (picked != null) await _openConversation(picked);
  }

  Future<void> _openConversation(String id) async {
    try {
      final result = await widget.api.loadConversation(id);
      if (!mounted) return;
      setState(() {
        _messages = result.data;
        _conversationId = id;
        _fromCache = result.fromCache;
        _notice = null;
      });
      _scrollDown();
    } on ChatException catch (e) {
      if (mounted) setState(() => _notice = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Column(
      children: [
        _buildToolbar(),
        if (_fromCache) _banner('Sin conexión · conversación guardada en el dispositivo', AppColors.orange, key: 'chat-cache-banner'),
        if (_notice != null) _banner(_notice!.message, _notice!.kind == ChatErrorKind.quota ? AppColors.orange : const Color(0xFFEF4444), key: 'chat-notice'),
        Expanded(child: _messages.isEmpty ? _buildExamples() : _buildMessages()),
        _buildInput(),
      ],
    );
  }

  Widget _banner(String text, Color color, {required String key}) => Container(
        key: Key(key),
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: color.withValues(alpha: 0.5)),
        ),
        child: Text(text, style: TextStyle(color: color, fontSize: 12)),
      );

  Widget _buildToolbar() => Row(
        children: [
          if (_usage != null)
            Expanded(
              child: Text('Preguntas hoy: ${_usage!.usadas}/${_usage!.limite}',
                  key: const Key('chat-usage'), style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
            )
          else
            const Spacer(),
          TextButton.icon(
            key: const Key('chat-history'),
            onPressed: _openHistory,
            icon: const Icon(Icons.history, size: 18),
            label: const Text('Historial'),
          ),
          TextButton.icon(
            key: const Key('chat-new'),
            onPressed: _sending ? null : _newConversation,
            icon: const Icon(Icons.add_comment_outlined, size: 18),
            label: const Text('Nueva'),
          ),
        ],
      );

  Widget _buildExamples() => ListView(
        children: [
          const SizedBox(height: 24),
          const Icon(Icons.travel_explore, size: 44, color: AppColors.teal),
          const SizedBox(height: 10),
          const Text('Pregunta por la competencia',
              textAlign: TextAlign.center, style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 6),
          const Text(
            'Respondo con los datos de Enci-Intel y siempre te digo de dónde salió cada dato. '
            'Si no lo sé, te lo digo.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textMuted, fontSize: 13),
          ),
          const SizedBox(height: 18),
          for (var i = 0; i < exampleQuestions.length; i++)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: OutlinedButton(
                key: Key('example-$i'),
                onPressed: _sending ? null : () => _send(exampleQuestions[i]),
                style: OutlinedButton.styleFrom(
                  alignment: Alignment.centerLeft,
                  padding: const EdgeInsets.all(14),
                  side: const BorderSide(color: AppColors.border),
                ),
                child: Text(exampleQuestions[i], style: const TextStyle(color: AppColors.textSoft, fontSize: 13)),
              ),
            ),
        ],
      );

  Widget _buildMessages() => ListView.builder(
        controller: _scroll,
        itemCount: _messages.length,
        itemBuilder: (context, i) {
          final message = _messages[i];
          final waiting = !message.isUser && message.text.isEmpty && _sending && i == _messages.length - 1;
          return _Bubble(
            key: Key('chat-bubble-$i'),
            message: message,
            waitingText: waiting ? (_status ?? 'Pensando…') : null,
            onFeedback: (value) => _feedback(message, value),
          );
        },
      );

  Widget _buildInput() => Padding(
        padding: const EdgeInsets.only(top: 6, bottom: 8),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('chat-input'),
                controller: _controller,
                enabled: !_sending,
                minLines: 1,
                maxLines: 4,
                maxLength: 1000,
                textInputAction: TextInputAction.send,
                onSubmitted: _send,
                style: const TextStyle(color: Colors.white),
                decoration: const InputDecoration(
                  isDense: true,
                  counterText: '',
                  hintText: 'Pregunta sobre la competencia…',
                  hintStyle: TextStyle(color: AppColors.textMuted),
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              key: const Key('chat-send'),
              onPressed: _sending ? null : () => _send(_controller.text),
              icon: const Icon(Icons.send),
            ),
          ],
        ),
      );
}

class _Bubble extends StatelessWidget {
  const _Bubble({super.key, required this.message, required this.onFeedback, this.waitingText});
  final ChatMessage message;
  final String? waitingText;
  final void Function(String value) onFeedback;

  @override
  Widget build(BuildContext context) {
    final user = message.isUser;
    return Align(
      alignment: user ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.of(context).size.width * 0.86),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: user ? AppColors.teal.withValues(alpha: 0.18) : AppColors.card,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: user ? AppColors.teal.withValues(alpha: 0.4) : AppColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (waitingText != null)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.teal)),
                  const SizedBox(width: 8),
                  Text(waitingText!, key: const Key('chat-status'), style: const TextStyle(color: AppColors.textMuted, fontSize: 13)),
                ],
              )
            else
              SelectableText(message.text, style: const TextStyle(color: Colors.white, height: 1.4)),
            if (message.sources.isNotEmpty) ...[
              const SizedBox(height: 10),
              for (final source in message.sources) _SourceTile(source: source),
            ],
            if (!user && message.index != null && !message.isError)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    key: Key('feedback-up-${message.index}'),
                    visualDensity: VisualDensity.compact,
                    icon: Icon(message.feedback == 'up' ? Icons.thumb_up : Icons.thumb_up_outlined, size: 18, color: AppColors.textMuted),
                    onPressed: () => onFeedback('up'),
                  ),
                  IconButton(
                    key: Key('feedback-down-${message.index}'),
                    visualDensity: VisualDensity.compact,
                    icon: Icon(message.feedback == 'down' ? Icons.thumb_down : Icons.thumb_down_outlined, size: 18, color: AppColors.textMuted),
                    onPressed: () => onFeedback('down'),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

/// Fuente citada: la etiqueta distingue el dato interno (Enci-Intel) del que viene de internet.
class _SourceTile extends StatelessWidget {
  const _SourceTile({required this.source});
  final ChatSource source;

  @override
  Widget build(BuildContext context) {
    final color = source.isWeb ? AppColors.orange : AppColors.teal;
    final date = parseUtc(source.fecha);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.18), borderRadius: BorderRadius.circular(6)),
            child: Text(source.originLabel, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w700)),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  [source.titulo, if (date != null) timeAgo(date)].join(' · '),
                  style: const TextStyle(color: AppColors.textSoft, fontSize: 12),
                ),
                if ((source.url ?? '').isNotEmpty)
                  SelectableText(source.url!, style: TextStyle(color: color, fontSize: 11)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HistorySheet extends StatefulWidget {
  const _HistorySheet({required this.api, required this.currentId, required this.onDeleted});
  final CompetenciaChatApi api;
  final String? currentId;
  final void Function(String id) onDeleted;

  @override
  State<_HistorySheet> createState() => _HistorySheetState();
}

class _HistorySheetState extends State<_HistorySheet> {
  List<ConversationSummary> _items = [];
  bool _loading = true;
  bool _fromCache = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final result = await widget.api.conversations();
      if (!mounted) return;
      setState(() {
        _items = result.data;
        _fromCache = result.fromCache;
        _loading = false;
      });
    } on ChatException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _delete(ConversationSummary item) async {
    try {
      await widget.api.deleteConversation(item.id);
      widget.onDeleted(item.id);
      if (mounted) setState(() => _items = _items.where((c) => c.id != item.id).toList());
    } on ChatException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      key: const Key('chat-history-sheet'),
      height: MediaQuery.of(context).size.height * 0.6,
      child: Column(
        children: [
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text('Conversaciones', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
          ),
          if (_fromCache)
            const Padding(
              padding: EdgeInsets.only(bottom: 8),
              child: Text('Sin conexión · historial guardado', style: TextStyle(color: AppColors.orange, fontSize: 12)),
            ),
          if (_error != null) Padding(padding: const EdgeInsets.all(12), child: Text(_error!, style: const TextStyle(color: AppColors.textMuted))),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator(color: AppColors.teal))
                : _items.isEmpty
                    ? const Center(child: Text('Aún no tienes conversaciones.', style: TextStyle(color: AppColors.textMuted)))
                    : ListView(
                        children: [
                          for (final item in _items)
                            ListTile(
                              key: Key('history-${item.id}'),
                              selected: item.id == widget.currentId,
                              title: Text(item.titulo, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Colors.white)),
                              subtitle: Text('${item.mensajes ~/ 2} preguntas', style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
                              trailing: IconButton(
                                key: Key('history-delete-${item.id}'),
                                icon: const Icon(Icons.delete_outline, color: AppColors.textMuted),
                                onPressed: () => _delete(item),
                              ),
                              onTap: () => Navigator.of(context).pop(item.id),
                            ),
                        ],
                      ),
          ),
        ],
      ),
    );
  }
}
