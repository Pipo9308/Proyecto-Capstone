# Enci Vendedor (app Flutter)

App móvil para vendedores de Encipharm. Habla solo con el backend de Enci-Ventas
(`/inteligencia/*` incluido: el backend consulta a Enci-Intel por detrás).

## Requisitos
- Flutter 3.47 o superior (Dart `^3.12.2`).

## Servidor al que se conecta
La URL se define al compilar con `--dart-define=API_URL=...` (por defecto `http://10.0.2.2:8000`,
que solo sirve en el emulador de Android contra el compose local).

```bash
flutter pub get
flutter run --dart-define=API_URL=http://10.0.2.2:8000            # emulador Android + docker compose local
flutter run --dart-define=API_URL=http://192.168.1.50:8000        # celular físico en la misma red

flutter build apk --release --dart-define=API_URL=https://<servidor-de-produccion>
flutter build appbundle --release --dart-define=API_URL=https://<servidor-de-produccion>
```

Un build **release** se niega a iniciar si `API_URL` apunta a localhost, a una red local o
no usa HTTPS, y muestra el motivo en pantalla.

## Calidad
```bash
flutter analyze
flutter test
```

## Inteligencia (RQ-09)
La pestaña **Inteligencia** solo aparece si el admin activó "Acceso a Inteligencia" para el
usuario (el admin siempre lo tiene). Muestra el feed de alertas de la competencia y la ficha
de productos del registro SAG. Sin conexión usa una copia local: las últimas 100 alertas y las
fichas vistas en los últimos 7 días; esa copia se borra al cerrar sesión.
