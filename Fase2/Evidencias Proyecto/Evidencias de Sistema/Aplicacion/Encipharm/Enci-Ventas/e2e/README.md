# Pruebas E2E de Enci Ventas

Playwright con un navegador real (Edge, que ya viene en Windows) contra el stack local: web (`:5173`), API (`:8000`) y el
emulador de Firestore del compose de Ventas (`:8086`). **Nunca apuntan a producción**: cada archivo empieza vaciando el
emulador y volviendo a sembrar los datos de demostración.

## Cómo correrlas

```bash
# 1. Stack local arriba (desde la raiz del repo)
docker compose up -d firestore backend frontend redis azurite intel-backend

# 2. Pruebas
cd Enci-Ventas/e2e
npm install
npm test                      # todas (~3 min)
npx playwright test tests/clientes.spec.ts            # un archivo
npx playwright test -g "RUT repetido"                 # una prueba
npm run test:headed           # viendo el navegador
npm run report                # informe HTML de la ultima corrida
```

Variables opcionales: `E2E_BASE_URL`, `E2E_API_URL`, `E2E_FIRESTORE_URL`, `E2E_FIREBASE_PROJECT` (por defecto `enci-local`),
`DOCKER_BIN` (carpeta del CLI de Docker) y `E2E_BROWSER_CHANNEL` (`msedge` por defecto; vacío usa el Chromium de Playwright,
que se instala con `npx playwright install chromium`).

## Qué cubren (35 pruebas)

| Archivo | Flujos |
|---|---|
| `auth` | Login válido e inválido, rutas protegidas, cerrar sesión |
| `roles` | Menú y acceso por rol (admin, supervisor, vendedor con y sin Inteligencia), URLs escritas a mano |
| `clientes` | Crear cliente, RUT repetido y con dígito malo, búsqueda, el admin ve al instante lo que crea el vendedor, aislamiento entre vendedores |
| `comercial` | Oportunidad → propuesta con descuento → aprobación del supervisor → aviso al vendedor; dashboard |
| `calendario` | Agendar, fin que acompaña al inicio, límite de 12 h, «realizada» queda en el historial, arrastrar a otro día, filtro del supervisor |
| `competencia` | Comparación por precio por unidad, reportar → aprobar → cambia la comparación, descartar, alta de catálogo |
| `notificaciones` | Contador, abrir un aviso lo marca y navega, marcar todas, privacidad entre usuarios |
| `inteligencia` | Pantalla de alertas y chat (con el error claro cuando no hay modelo configurado) |

## Notas

- Las pruebas corren **de a una** (`workers: 1`) porque comparten la base. Cada archivo es independiente de los demás.
- Los usuarios de prueba salen de `Backend/scripts/seed_admin.py` y `seed_demo_fase4.py`.
- Los avisos de visitas dependen del reloj del servidor (se calculan al consultar y como máximo una vez por minuto): la
  preparación de `notificaciones` espera hasta que aparezcan.
- No están en el CI de GitHub: necesitan el stack completo. Para sumarlas habría que levantar compose en el job.
- No cubren: subida de PDF a una propuesta (Azurite), documentos del RAG, el chat con un modelo real (falta `DEEPSEEK_API_KEY`)
  ni la app Flutter.
