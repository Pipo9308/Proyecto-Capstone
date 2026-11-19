import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'core/api_config.dart';
import 'pages/nueva_cotizacion.dart';
import 'pages/home_page.dart';
import 'theme/app_colors.dart';
import 'pages/forecast_page.dart';
import 'pages/login_page.dart';
import 'pages/config_page.dart';
import 'pages/pipeline_page.dart';
import 'pages/inteligencia_page.dart';
import 'pages/rag_page.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'services/intel_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Un release nunca debe apuntar a localhost ni a HTTP: se muestra el motivo en vez de fallar en silencio.
  final configError = releaseConfigError(baseUrl: ApiService.baseUrl, isRelease: kReleaseMode);
  runApp(configError == null ? const EnciApp() : ConfigErrorApp(message: configError));
}

class ConfigErrorApp extends StatelessWidget {
  const ConfigErrorApp({super.key, required this.message});
  final String message;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        backgroundColor: const Color(0xFF0F172A),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.orangeAccent, fontSize: 16),
            ),
          ),
        ),
      ),
    );
  }
}

class EnciApp extends StatelessWidget {
  const EnciApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Enci Vendedor',
      theme: ThemeData(
        fontFamily: 'Arial',
        scaffoldBackgroundColor: AppColors.background,
        colorScheme: ColorScheme.fromSeed(seedColor: AppColors.green),
      ),
      home: const AuthGate(),
    );
  }
}

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  bool loggedIn = false;
  bool _restoring = true;

  @override
  void initState() {
    super.initState();
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    var restored = false;
    if (await AuthService().restoreSession()) {
      // Habia un token guardado: se confirma contra el backend. Si esta
      // vencido o ya no tiene acceso (401/403), se descarta y se pide login.
      restored = await ApiService.verificarAcceso();
      if (!restored) {
        await AuthService().signOut();
      }
    }
    if (!mounted) return;
    setState(() {
      loggedIn = restored;
      _restoring = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_restoring) {
      return const Scaffold(
        backgroundColor: Color(0xFF0F172A),
        body: Center(
          child: CircularProgressIndicator(color: Color(0xFF0D9488)),
        ),
      );
    }
    if (loggedIn) {
      return const MainShell();
    }
    return LoginPage(
      onLoginSuccess: () {
        setState(() {
          loggedIn = true;
        });
      },
    );
  }
}

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int index = 0;
  bool? _tieneAcceso;
  int _intelUnread = 0;

  @override
  void initState() {
    super.initState();
    _verificar();
  }

  Future<void> _verificar() async {
    final acceso = await ApiService.verificarAcceso();
    if (!mounted) return;
    setState(() => _tieneAcceso = acceso);
    if (acceso) {
      // El admin pudo cambiar el rol o el permiso de Inteligencia desde el ultimo login.
      await AuthService().refreshProfile();
      if (!mounted) return;
      setState(() {});
      await _refreshIntelUnread();
    }
  }

  Future<void> _refreshIntelUnread() async {
    if (!AuthService().hasIntelAccess) return;
    try {
      final unread = await IntelService().unreadCount();
      if (!mounted) return;
      setState(() => _intelUnread = unread);
    } catch (_) {
      // Sin Intel o sin red el contador simplemente no se muestra.
    }
  }

  void _logout() {
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => const AuthGate()),
    );
  }

  @override
  Widget build(BuildContext context) {
    // Cargando verificacion
    if (_tieneAcceso == null) {
      return const Scaffold(
        backgroundColor: Color(0xFF0F172A),
        body: Center(
          child: CircularProgressIndicator(color: Color(0xFF0D9488)),
        ),
      );
    }

    // Sin acceso
    if (!_tieneAcceso!) {
      return Scaffold(
        backgroundColor: const Color(0xFF0F172A),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.lock_outline,
                    color: Colors.orangeAccent, size: 80),
                const SizedBox(height: 24),
                const Text(
                  'Sin acceso',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Tu cuenta no tiene permisos para acceder al sistema Enci Ventas.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Color(0xFF94A3B8), fontSize: 15),
                ),
                const SizedBox(height: 24),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E293B),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: const Color(0xFF334155)),
                  ),
                  child: const Text(
                    '📧 Contacta al administrador de ENCI para que te asigne un rol en el sistema.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13),
                  ),
                ),
                const SizedBox(height: 32),
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton.icon(
                    onPressed: () async {
                      await AuthService().signOut();
                      _logout();
                    },
                    icon: const Icon(Icons.logout, color: Colors.redAccent),
                    label: const Text('Cerrar sesión',
                        style: TextStyle(color: Colors.redAccent)),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: Colors.redAccent),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    // Con acceso — app normal. La pestaña Inteligencia solo existe con el permiso
    // "Acceso a Inteligencia" (se inserta antes de Config).
    final hasIntel = AuthService().hasIntelAccess;
    final configIndex = hasIntel ? 6 : 5;
    final pages = [
      // El indice logico 5 de las tarjetas de Inicio es Config.
      HomePage(onNavigate: (value) => setState(() => index = value == 5 ? configIndex : value)),
      NuevaCotizacionPage(onSettingsTap: () => setState(() => index = configIndex)),
      ForecastPage(onSettingsTap: () => setState(() => index = configIndex)),
      PipelinePage(onSettingsTap: () => setState(() => index = configIndex)),
      RagPage(onSettingsTap: () => setState(() => index = configIndex)),
      if (hasIntel) InteligenciaPage(onUnreadChanged: _refreshIntelUnread),
      ConfigPage(onLogout: () {
        setState(() => index = 0);
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const AuthGate()),
        );
      }),
    ];

    // Si se revoca el permiso mientras la pestaña esta abierta, se vuelve a Inicio.
    final currentIndex = index < pages.length ? index : 0;

    return Scaffold(
      body: SafeArea(child: pages[currentIndex]),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: currentIndex,
        onTap: (value) => setState(() => index = value),
        backgroundColor: const Color(0xFF0F172A),
        selectedItemColor: AppColors.teal,
        unselectedItemColor: AppColors.textSoft,
        type: BottomNavigationBarType.fixed,
        items: [
          const BottomNavigationBarItem(icon: Icon(Icons.home_outlined), label: 'Inicio'),
          const BottomNavigationBarItem(icon: Icon(Icons.add), label: 'Nuevo'),
          const BottomNavigationBarItem(icon: Icon(Icons.trending_up), label: 'Forecast'),
          const BottomNavigationBarItem(icon: Icon(Icons.filter_alt_outlined), label: 'Pipeline'),
          const BottomNavigationBarItem(icon: Icon(Icons.auto_awesome), label: 'IA RAG'),
          if (hasIntel)
            BottomNavigationBarItem(
              icon: Badge(
                label: Text('$_intelUnread'),
                isLabelVisible: _intelUnread > 0,
                child: const Icon(Icons.radar),
              ),
              label: 'Inteligencia',
            ),
          const BottomNavigationBarItem(icon: Icon(Icons.settings_outlined), label: 'Config'),
        ],
      ),
    );
  }
}

Widget pagePlaceholder(String tag, String title, String desc) {
  return Padding(
    padding: const EdgeInsets.all(22),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(tag, style: const TextStyle(color: AppColors.teal, fontWeight: FontWeight.bold)),
        const SizedBox(height: 10),
        Text(title, style: const TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.bold)),
        const SizedBox(height: 10),
        Text(desc, style: const TextStyle(color: Color(0xFFBFDBFE), fontSize: 17)),
      ],
    ),
  );
}