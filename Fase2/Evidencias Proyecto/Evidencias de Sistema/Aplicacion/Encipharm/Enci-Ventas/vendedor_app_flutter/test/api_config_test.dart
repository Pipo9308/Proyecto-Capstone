import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_vendedor/core/api_config.dart';

void main() {
  group('isLocalUrl', () {
    test('detecta direcciones de desarrollo', () {
      for (final url in [
        'http://localhost:8000',
        'http://10.0.2.2:8000',
        'http://127.0.0.1:8000',
        'http://192.168.1.50:8000',
        'http://172.20.0.5:8000',
        'http://10.1.2.3',
        'http://mi-pc.local:8000',
        '',
      ]) {
        expect(isLocalUrl(url), isTrue, reason: url);
      }
    });

    test('no marca como locales los servidores publicos', () {
      expect(isLocalUrl('https://api.encipharm.cl'), isFalse);
      expect(isLocalUrl('https://enci-ventas.onrender.com'), isFalse);
      expect(isLocalUrl('https://172.32.0.1'), isFalse);
    });
  });

  group('releaseConfigError', () {
    test('en debug nunca bloquea', () {
      expect(releaseConfigError(baseUrl: 'http://10.0.2.2:8000', isRelease: false), isNull);
    });

    test('un release apuntando a localhost se bloquea con una explicacion', () {
      final error = releaseConfigError(baseUrl: 'http://10.0.2.2:8000', isRelease: true);
      expect(error, contains('--dart-define=API_URL'));
    });

    test('un release exige HTTPS', () {
      expect(releaseConfigError(baseUrl: 'http://api.encipharm.cl', isRelease: true), contains('HTTPS'));
    });

    test('un release con HTTPS publico es valido', () {
      expect(releaseConfigError(baseUrl: 'https://api.encipharm.cl', isRelease: true), isNull);
    });
  });
}
