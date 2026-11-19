/// Una URL de desarrollo (emulador, localhost o red local) no sirve en un build de produccion.
bool isLocalUrl(String url) {
  final host = Uri.tryParse(url)?.host.toLowerCase() ?? '';
  if (host.isEmpty) return true;
  if (host == 'localhost' || host == '10.0.2.2' || host == '127.0.0.1' || host == '0.0.0.0') return true;
  if (host.endsWith('.local')) return true;
  // Rangos privados: 10.x.x.x, 192.168.x.x y 172.16-31.x.x
  final octets = host.split('.');
  if (octets.length == 4 && octets.every((o) => int.tryParse(o) != null)) {
    final first = int.parse(octets[0]);
    final second = int.parse(octets[1]);
    return first == 10 || (first == 192 && second == 168) || (first == 172 && second >= 16 && second <= 31);
  }
  return false;
}

/// Devuelve el motivo por el que la configuracion no es valida, o null si esta bien.
/// Un build release nunca puede apuntar a localhost ni usar HTTP sin cifrar
/// (RF-09.02): se compila con `--dart-define=API_URL=https://...`.
String? releaseConfigError({required String baseUrl, required bool isRelease}) {
  if (!isRelease) return null;
  if (isLocalUrl(baseUrl)) {
    return 'Esta versión de la app apunta a un servidor de desarrollo ($baseUrl). '
        'Compílala con --dart-define=API_URL=https://<servidor-de-produccion>.';
  }
  if (Uri.tryParse(baseUrl)?.scheme != 'https') {
    return 'La URL del servidor debe usar HTTPS ($baseUrl).';
  }
  return null;
}
