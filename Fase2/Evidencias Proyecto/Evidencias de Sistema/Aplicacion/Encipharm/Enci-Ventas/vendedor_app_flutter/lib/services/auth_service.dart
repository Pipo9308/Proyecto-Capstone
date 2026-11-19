import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'api_service.dart';
import 'chat_cache.dart';
import 'intel_cache.dart';

class AuthService {
  static final AuthService _instance = AuthService._internal();
  factory AuthService() => _instance;
  AuthService._internal();

  // El token se persiste en el almacenamiento seguro del dispositivo para que
  // la sesion sobreviva a que Android mate la app en segundo plano.
  static const FlutterSecureStorage _storage = FlutterSecureStorage();
  static const String _kToken = 'enci_jwt';
  static const String _kRole = 'enci_role';
  static const String _kName = 'enci_name';
  static const String _kIntel = 'enci_intel';

  String? _jwtToken;
  String _userRole = 'vendedor';
  String _userName = 'VENDEDOR';
  bool _intelAccess = false;

  String get userRole => _userRole;
  String get userName => _userName;

  /// Permiso "Acceso a Inteligencia": el admin siempre lo tiene. El backend es quien lo exige.
  bool get hasIntelAccess => _userRole == 'admin' || _intelAccess;

  Future<void> signIn(String email, String password) async {
    final dio = Dio(BaseOptions(baseUrl: ApiService.baseUrl));
    try {
      final res = await dio.post('/auth/login', data: {
        'email': email,
        'password': password,
      });
      _jwtToken = res.data['access_token'];
      if (res.data['user'] != null) {
        _userRole = res.data['user']['rol'] ?? 'vendedor';
        _userName = res.data['user']['nombre'] ?? 'VENDEDOR';
        _intelAccess = res.data['user']['accesoInteligencia'] == true;
      }
      await _persist();
    } catch (e) {
      if (e is DioException) {
        // El backend responde {error, codigo, detalles, timestamp}; 'detail' es de FastAPI por defecto.
        final data = e.response?.data;
        final message = data is Map ? (data['error'] ?? data['detail']) : null;
        throw Exception(message?.toString() ?? 'Fallo al iniciar sesión');
      }
      throw Exception('Error de conexión: $e');
    }
  }

  /// Avisa al administrador que el usuario quiere restablecer su contraseña (todavia no se envian
  /// correos: el admin le entrega un enlace). Devuelve el mensaje del backend.
  Future<String> requestPasswordReset(String email) async {
    final dio = Dio(BaseOptions(baseUrl: ApiService.baseUrl));
    try {
      final res = await dio.post('/auth/forgot-password', data: {'email': email.trim()});
      final data = res.data;
      return (data is Map ? data['mensaje'] : null)?.toString() ??
          'Solicitud enviada a tu administrador.';
    } on DioException {
      throw Exception('No se pudo enviar la solicitud. Revisa tu conexión e intenta de nuevo.');
    }
  }

  /// Recupera la sesion guardada. Devuelve true si habia un token; NO valida
  /// que siga vigente (eso lo confirma el backend en la primera llamada).
  Future<bool> restoreSession() async {
    try {
      final token = await _storage.read(key: _kToken);
      if (token == null || token.isEmpty) return false;
      _jwtToken = token;
      _userRole = await _storage.read(key: _kRole) ?? 'vendedor';
      _userName = await _storage.read(key: _kName) ?? 'VENDEDOR';
      _intelAccess = await _storage.read(key: _kIntel) == 'true';
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _persist() async {
    // Si el almacenamiento falla, el login igual funciona (solo se pierde la
    // persistencia).
    try {
      await _storage.write(key: _kToken, value: _jwtToken);
      await _storage.write(key: _kRole, value: _userRole);
      await _storage.write(key: _kName, value: _userName);
      await _storage.write(key: _kIntel, value: _intelAccess.toString());
    } catch (_) {}
  }

  Future<String?> getIdToken() async {
    return _jwtToken;
  }

  /// Vuelve a leer rol y permisos desde el backend (el admin pudo cambiarlos).
  /// Sin red se conserva lo guardado.
  Future<void> refreshProfile() async {
    try {
      final dio = await ApiService.authClient();
      final res = await dio.get('/users/me');
      _userRole = res.data['rol'] ?? _userRole;
      _userName = res.data['nombre'] ?? _userName;
      _intelAccess = res.data['accesoInteligencia'] == true;
      await _persist();
    } catch (_) {}
  }

  Future<void> signOut() async {
    _jwtToken = null;
    _intelAccess = false;
    // La copia local de Inteligencia no debe sobrevivir al cambio de usuario.
    await IntelCache().clear();
    await ChatCache().clear();
    try {
      await _storage.delete(key: _kToken);
      await _storage.delete(key: _kRole);
      await _storage.delete(key: _kName);
      await _storage.delete(key: _kIntel);
    } catch (_) {}
  }
}
