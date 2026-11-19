import 'dart:async';

import 'package:flutter/material.dart';

import '../models/intel_models.dart';
import '../services/competencia_chat_service.dart';
import '../services/intel_service.dart';
import '../theme/app_colors.dart';
import '../widgets/intel_widgets.dart';
import 'competencia_chat_view.dart';
import 'intel_product_page.dart';

class InteligenciaPage extends StatefulWidget {
  const InteligenciaPage({super.key, this.api, this.chatApi, this.onUnreadChanged});

  /// Se inyectan en los tests; por defecto usan el backend real.
  final IntelApi? api;
  final CompetenciaChatApi? chatApi;

  /// Se avisa al marcar alertas como leidas para refrescar el contador de la barra.
  final VoidCallback? onUnreadChanged;

  @override
  State<InteligenciaPage> createState() => _InteligenciaPageState();
}

class _InteligenciaPageState extends State<InteligenciaPage> with SingleTickerProviderStateMixin {
  late final TabController _tabs = TabController(length: 3, vsync: this);
  late final IntelApi _api = widget.api ?? IntelService();
  late final CompetenciaChatApi _chatApi = widget.chatApi ?? CompetenciaChatService();

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Inteligencia',
              style: TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.bold)),
          const Text('Alertas y registros SAG de la competencia',
              style: TextStyle(color: AppColors.textMuted, fontSize: 13)),
          const SizedBox(height: 8),
          TabBar(
            controller: _tabs,
            indicatorColor: AppColors.teal,
            labelColor: AppColors.teal,
            unselectedLabelColor: AppColors.textMuted,
            tabs: const [Tab(text: 'Alertas'), Tab(text: 'Productos'), Tab(text: 'Competencia IA')],
          ),
          const SizedBox(height: 8),
          Expanded(
            child: TabBarView(
              controller: _tabs,
              children: [
                _AlertsTab(api: _api, onUnreadChanged: widget.onUnreadChanged),
                _ProductsTab(api: _api),
                CompetenciaChatView(api: _chatApi),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Alertas ───────────────────────────────────────────────────────────────────

const _priorityFilters = <String?, String>{
  null: 'Todas',
  'critical': 'Crítica',
  'high': 'Alta',
  'medium': 'Media',
  'low': 'Baja',
};

const _typeFilters = <String?, String>{
  null: 'Todos los tipos',
  'NEWSKU': 'Nuevo registro',
  'CANCELACION': 'Cancelación',
  'NOTICIA': 'Noticia',
};

class _AlertsTab extends StatefulWidget {
  const _AlertsTab({required this.api, this.onUnreadChanged});
  final IntelApi api;
  final VoidCallback? onUnreadChanged;

  @override
  State<_AlertsTab> createState() => _AlertsTabState();
}

class _AlertsTabState extends State<_AlertsTab> with AutomaticKeepAliveClientMixin {
  static const _pageSize = 50;

  final ScrollController _scroll = ScrollController();
  final TextEditingController _competitor = TextEditingController();
  List<IntelAlert> _alerts = [];
  bool _loading = true;
  bool _loadingMore = false;
  bool _hasMore = false;
  bool _fromCache = false;
  DateTime? _cachedAt;
  IntelException? _error;
  String? _priority;
  String? _type;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _load();
  }

  @override
  void dispose() {
    _scroll.dispose();
    _competitor.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scroll.hasClients && _scroll.position.pixels >= _scroll.position.maxScrollExtent - 200) {
      _loadMore();
    }
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await widget.api.fetchAlerts(
        priority: _priority,
        type: _type,
        competitor: _competitor.text,
        limit: _pageSize,
      );
      if (!mounted) return;
      setState(() {
        _alerts = result.data.alerts;
        _hasMore = result.data.hasMore;
        _fromCache = result.fromCache;
        _cachedAt = result.cachedAt;
        _loading = false;
      });
    } on IntelException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || !_hasMore || _loading || _fromCache) return;
    setState(() => _loadingMore = true);
    try {
      final result = await widget.api.fetchAlerts(
        priority: _priority,
        type: _type,
        competitor: _competitor.text,
        offset: _alerts.length,
        limit: _pageSize,
      );
      if (!mounted) return;
      final known = _alerts.map((a) => a.id).toSet();
      setState(() {
        _alerts = [..._alerts, ...result.data.alerts.where((a) => !known.contains(a.id))];
        _hasMore = result.data.hasMore;
        _loadingMore = false;
      });
    } on IntelException {
      if (!mounted) return;
      setState(() => _loadingMore = false);
    }
  }

  Future<void> _open(IntelAlert alert) async {
    if (!alert.leida) {
      setState(() => _alerts = _alerts.map((a) => a.id == alert.id ? a.copyWith(leida: true) : a).toList());
      await widget.api.markRead(alert.id);
      widget.onUnreadChanged?.call();
    }
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.card,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => _AlertDetail(alert: alert),
    );
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Column(
      children: [
        _buildFilters(),
        if (_fromCache) OfflineBanner(cachedAt: _cachedAt),
        Expanded(child: _buildBody()),
      ],
    );
  }

  Widget _buildFilters() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final entry in _priorityFilters.entries)
                Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: ChoiceChip(
                    key: Key('priority-chip-${entry.key ?? 'all'}'),
                    label: Text(entry.value),
                    selected: _priority == entry.key,
                    onSelected: (_) {
                      setState(() => _priority = entry.key);
                      _load();
                    },
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('competitor-field'),
                controller: _competitor,
                style: const TextStyle(color: Colors.white),
                textInputAction: TextInputAction.search,
                onSubmitted: (_) => _load(),
                decoration: const InputDecoration(
                  isDense: true,
                  hintText: 'Competidor',
                  hintStyle: TextStyle(color: AppColors.textMuted),
                  prefixIcon: Icon(Icons.search, size: 18, color: AppColors.textMuted),
                ),
              ),
            ),
            const SizedBox(width: 8),
            DropdownButton<String?>(
              key: const Key('type-filter'),
              value: _type,
              dropdownColor: AppColors.card,
              style: const TextStyle(color: AppColors.textSoft, fontSize: 13),
              underline: const SizedBox.shrink(),
              items: [
                for (final entry in _typeFilters.entries)
                  DropdownMenuItem<String?>(value: entry.key, child: Text(entry.value)),
              ],
              onChanged: (value) {
                setState(() => _type = value);
                _load();
              },
            ),
          ],
        ),
        const SizedBox(height: 6),
      ],
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator(color: AppColors.teal));
    if (_error != null) return IntelErrorView(error: _error!, onRetry: _load);
    return RefreshIndicator(
      onRefresh: _load,
      child: _alerts.isEmpty
          ? ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: const [
                SizedBox(height: 80),
                Center(
                  child: Text('No hay alertas con estos filtros.', style: TextStyle(color: AppColors.textMuted)),
                ),
              ],
            )
          : ListView.builder(
              controller: _scroll,
              physics: const AlwaysScrollableScrollPhysics(),
              itemCount: _alerts.length + (_hasMore ? 1 : 0),
              itemBuilder: (context, index) {
                if (index >= _alerts.length) {
                  return const Padding(
                    padding: EdgeInsets.all(16),
                    child: Center(child: CircularProgressIndicator(color: AppColors.teal, strokeWidth: 2)),
                  );
                }
                return _AlertCard(alert: _alerts[index], onTap: () => _open(_alerts[index]));
              },
            ),
    );
  }
}

class _AlertCard extends StatelessWidget {
  const _AlertCard({required this.alert, required this.onTap});
  final IntelAlert alert;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = priorityColor(alert.priority);
    return Card(
      key: Key('intel-alert-${alert.id}'),
      color: AppColors.card,
      margin: const EdgeInsets.only(bottom: 8),
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: AppColors.border),
      ),
      child: InkWell(
        onTap: onTap,
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(width: 5, color: color),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          if (!alert.leida)
                            Container(
                              key: Key('unread-dot-${alert.id}'),
                              width: 8,
                              height: 8,
                              margin: const EdgeInsets.only(right: 6),
                              decoration: const BoxDecoration(color: AppColors.teal, shape: BoxShape.circle),
                            ),
                          Expanded(
                            child: Text(
                              alert.title,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: Colors.white,
                                fontWeight: alert.leida ? FontWeight.normal : FontWeight.bold,
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 8,
                        runSpacing: 4,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          _Tag(label: priorityLabel(alert.priority), color: color),
                          _Tag(label: alertTypeLabel(alert.subtype), color: AppColors.textMuted),
                          if ((alert.competitor ?? '').isNotEmpty)
                            Text(alert.competitor!, style: const TextStyle(color: AppColors.textSoft, fontSize: 12)),
                          Text(
                            [alert.source, timeAgo(alert.createdAt)].where((e) => (e ?? '').isNotEmpty).join(' · '),
                            style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag({required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(label, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }
}

class _AlertDetail extends StatelessWidget {
  const _AlertDetail({required this.alert});
  final IntelAlert alert;

  @override
  Widget build(BuildContext context) {
    final rows = alert.data.entries
        .where((e) => e.value != null && e.value.toString().trim().isNotEmpty)
        .take(16)
        .toList();
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.7,
      maxChildSize: 0.95,
      builder: (context, controller) => ListView(
        key: const Key('intel-alert-detail'),
        controller: controller,
        padding: const EdgeInsets.all(20),
        children: [
          Text(alert.title, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              _Tag(label: priorityLabel(alert.priority), color: priorityColor(alert.priority)),
              _Tag(label: alertTypeLabel(alert.subtype), color: AppColors.textMuted),
              if ((alert.competitor ?? '').isNotEmpty) _Tag(label: alert.competitor!, color: AppColors.blue),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            [
              if ((alert.source ?? '').isNotEmpty) 'Fuente: ${alert.source}',
              if (alert.createdAt != null) 'Llegó ${timeAgo(alert.createdAt)} (${formatDate(alert.createdAt!)})',
            ].join(' · '),
            style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
          ),
          if ((alert.description ?? '').isNotEmpty) ...[
            const SizedBox(height: 14),
            Text(alert.description!, style: const TextStyle(color: AppColors.textSoft, height: 1.4)),
          ],
          if (rows.isNotEmpty) ...[
            const SizedBox(height: 18),
            const Text('Datos de origen',
                style: TextStyle(color: AppColors.teal, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            for (final row in rows)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      width: 130,
                      child: Text(row.key, style: const TextStyle(color: AppColors.textMuted, fontSize: 12)),
                    ),
                    Expanded(
                      child: Text(row.value.toString(), style: const TextStyle(color: Colors.white, fontSize: 13)),
                    ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}

// ── Productos ─────────────────────────────────────────────────────────────────

class _ProductsTab extends StatefulWidget {
  const _ProductsTab({required this.api});
  final IntelApi api;

  @override
  State<_ProductsTab> createState() => _ProductsTabState();
}

class _ProductsTabState extends State<_ProductsTab> with AutomaticKeepAliveClientMixin {
  Timer? _debounce;
  List<ProductSummary> _results = [];
  bool _searching = false;
  bool _searched = false;
  bool _fromCache = false;
  IntelException? _error;
  String _query = '';

  @override
  bool get wantKeepAlive => true;

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _onChanged(String value) {
    _query = value;
    _debounce?.cancel();
    if (value.trim().length < 2) {
      setState(() {
        _results = [];
        _searched = false;
        _error = null;
      });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 400), _search);
  }

  Future<void> _search() async {
    final query = _query.trim();
    setState(() {
      _searching = true;
      _error = null;
    });
    try {
      final result = await widget.api.searchProducts(query);
      if (!mounted || query != _query.trim()) return;
      setState(() {
        _results = result.data;
        _fromCache = result.fromCache;
        _searched = true;
        _searching = false;
      });
    } on IntelException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _searching = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Column(
      children: [
        TextField(
          key: const Key('product-search-field'),
          style: const TextStyle(color: Colors.white),
          onChanged: _onChanged,
          decoration: const InputDecoration(
            isDense: true,
            hintText: 'Nombre, principio activo, titular o N° de registro',
            hintStyle: TextStyle(color: AppColors.textMuted, fontSize: 13),
            prefixIcon: Icon(Icons.search, size: 18, color: AppColors.textMuted),
          ),
        ),
        const SizedBox(height: 8),
        if (_fromCache) const OfflineBanner(cachedAt: null),
        Expanded(child: _buildBody()),
      ],
    );
  }

  Widget _buildBody() {
    if (_searching) return const Center(child: CircularProgressIndicator(color: AppColors.teal));
    if (_error != null) return IntelErrorView(error: _error!, onRetry: _search);
    if (!_searched) {
      return const Center(
        child: Text('Busca un producto o competidor del registro SAG.', style: TextStyle(color: AppColors.textMuted)),
      );
    }
    if (_results.isEmpty) {
      return const Center(child: Text('Sin resultados.', style: TextStyle(color: AppColors.textMuted)));
    }
    return ListView.builder(
      itemCount: _results.length,
      itemBuilder: (context, index) {
        final product = _results[index];
        final cancelled = (product.estado ?? '') == 'cancelado';
        return ListTile(
          key: Key('product-${product.registro}'),
          title: Text(product.nombreComercial ?? product.registro, style: const TextStyle(color: Colors.white)),
          subtitle: Text(
            [product.principioActivo, product.titular].where((e) => (e ?? '').isNotEmpty).join(' · '),
            style: const TextStyle(color: AppColors.textMuted, fontSize: 12),
          ),
          trailing: cancelled ? const _Tag(label: 'Cancelado', color: Color(0xFFEF4444)) : null,
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(builder: (_) => IntelProductPage(registro: product.registro, api: widget.api)),
          ),
        );
      },
    );
  }
}
