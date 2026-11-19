import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_vendedor/pages/login_page.dart';

Future<void> pumpLogin(WidgetTester tester, PasswordResetRequester requester) async {
  tester.view.physicalSize = const Size(800, 1800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: LoginPage(onLoginSuccess: () {}, requestPasswordReset: requester)));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('el login ofrece recuperar la contraseña y la solicitud se envia con el correo escrito', (tester) async {
    final sent = <String>[];
    await pumpLogin(tester, (email) async {
      sent.add(email);
      return 'Tu administrador recibió la solicitud.';
    });

    await tester.enterText(find.byType(TextField).first, 'ana@enci.cl');
    await tester.tap(find.byKey(const Key('forgot-password')));
    await tester.pumpAndSettle();

    expect(find.text('Restablecer contraseña'), findsOneWidget);
    expect(tester.widget<TextField>(find.byKey(const Key('forgot-email'))).controller!.text, 'ana@enci.cl');

    await tester.tap(find.byKey(const Key('forgot-send')));
    await tester.pumpAndSettle();

    expect(sent, ['ana@enci.cl']);
    expect(find.text('Tu administrador recibió la solicitud.'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byKey(const Key('forgot-send'))).onPressed, isNull);
  });

  testWidgets('si no se puede enviar muestra el error y permite reintentar', (tester) async {
    await pumpLogin(tester, (email) async => throw Exception('No se pudo enviar la solicitud.'));

    await tester.tap(find.byKey(const Key('forgot-password')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('forgot-send')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('forgot-error')), findsOneWidget);
    expect(find.text('No se pudo enviar la solicitud.'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byKey(const Key('forgot-send'))).onPressed, isNotNull);
  });
}
