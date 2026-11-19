# Setup - Enci Ventas CRM Web

## Requisitos previos

- Python 3.12 o superior.
- Node.js 20 o superior.
- `uv` instalado globalmente.
- Docker (opcional, para levantar PostgreSQL local).
- Base de datos PostgreSQL en funcionamiento.

## Clonar el repositorio

```bash
git clone https://github.com/Chumajer14/Encipharm.git
cd Encipharm
```

## Levantar dependencias locales

Para desarrollo puedes usar el `docker-compose.yml` provisto en la raíz:

```bash
docker compose up -d
```

## Backend

```bash
cd Backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

El servidor queda disponible en:

- API: `http://127.0.0.1:8000`
- Swagger UI no-produccion: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`
- Readiness: `http://127.0.0.1:8000/readiness` (requiere sesion de admin)

### Variables de entorno backend

Crear `Backend/.env` desde `Backend/.env.example`.

Valores minimos:

```env
APP_ENV=development            # sin esto el backend arranca como production (sin /docs)
FIREBASE_PROJECT_ID=enci-local
FIRESTORE_EMULATOR_HOST=localhost:8085   # emulador: gcloud emulators firestore start --host-port=0.0.0.0:8085
JWT_SECRET=una-clave-aleatoria-larga
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Opcionales:

- `LOG_LEVEL` (`INFO`) y `LOG_FORMAT` (`json` o `text`; usar `text` en local).
- `NOTIFICATIONS_INTEL_POLL_SECONDS` (120; 0 apaga el sondeo de alertas de Intel) y `NOTIFICATIONS_INTEL_LOOKBACK_HOURS` (72).
- `ENCI_INTEL_API_URL` y `ENCI_INTEL_API_KEY` para la integracion con Enci-Intel.
- `DEEPSEEK_API_KEY` (chat RAG y chat de competencia) y `TAVILY_API_KEY` + `WEB_SEARCH_ENABLED=true` para la busqueda web.

Para UAT, staging o produccion:

- `CORS_ORIGINS` solo con dominios publicados.
- `FIREBASE_PROJECT_ID` real, `FIREBASE_CREDENTIALS_JSON` (JSON de la cuenta de servicio en una linea) y `JWT_SECRET` aleatoria generada de manera segura (rotarlas si alguna vez estuvieron en un repositorio).
- `DEEPSEEK_API_KEY` configurada si se usara `/rag/chat`.

## Frontend

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

El frontend queda disponible en `http://127.0.0.1:5173`.

### Variables de entorno frontend

Crear `frontend/.env` desde `frontend/.env.example`.

```env
VITE_APP_NAME=Enci Ventas
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## App Vendedor (Flutter)

```bash
cd vendedor_app_flutter
flutter pub get
flutter run
```



## Seed demo

Para cargar datos comerciales de prueba al usuario `vendedor.demo@enci.cl`:

```bash
cd Backend
uv run python scripts/seed_max_wellq_demo.py --apply
```

El seed crea clientes, oportunidades, propuestas e interacciones deterministicas para pruebas funcionales.

## Verificacion local

### Backend

```bash
cd Backend
uv run pytest
```

Suite focal de cierre:

```bash
python -m pytest Backend\tests\test_clientes_permissions.py Backend\tests\test_readiness.py Backend\tests\test_security_hardening.py
```

### Frontend

```bash
cd frontend
npm audit --audit-level=low
npm run lint
npm run build
```

## Smoke test de ambiente publicado

```bash
python tools/smoke_crm_web.py --env uat --api-base-url https://api.example.com --web-url https://crm.example.com
```

Con token real:

```bash
python tools/smoke_crm_web.py --env uat --api-base-url https://api.example.com --web-url https://crm.example.com --token <jwt_token>
```

## Endpoints actuales

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/` | Root API |
| GET | `/health` | Estado basico del servidor |
| GET | `/readiness` | Revision de configuracion de UAT/go-live (solo admin) |
| GET | `/me` | Usuario autenticado |
| POST | `/auth/login` | Login/sync de usuario autenticado |
| GET/POST | `/clientes` | Listado y alta de clientes |
| GET/PATCH/DELETE | `/clientes/{id}` | Detalle, edicion y baja logica |
| POST | `/clientes/import-csv` | Importacion CSV admin |
| GET/POST | `/interacciones` | Interacciones comerciales |
| GET/POST/PATCH | `/oportunidades` | Oportunidades y pipeline |
| GET/POST/PATCH | `/propuestas` | Propuestas comerciales |
| GET/PATCH | `/users` | Gestion de usuarios |
| POST/GET | `/rag/*` | Asistente documental |

## Ramas

| Rama | Proposito |
|------|-----------|
| `main` | Base estable |
| `cierre-proyecto` | Cierre CRM web y documentacion |
| `feature/*` | Trabajo acotado por modulo |

## Solución de Problemas (Troubleshooting)

### Códigos de error de conexión (Frontend web)
- `API_NETWORK_FETCH_FAILED`: el navegador no pudo ejecutar `fetch`. Causas probables: CORS, DNS, red bloqueada, extensión del navegador o URL inaccesible.
- `API_HTTP_<status>`: Vercel respondió con HTTP no exitoso y el backend/proxy no entregó un código más específico.
- `API_ERROR_BODY_NOT_JSON`: el servidor devolvió un error en HTML/texto en vez de JSON.
- `API_SUCCESS_BODY_NOT_JSON`: la respuesta fue `2xx`, pero el cuerpo no era JSON válido.

### Códigos de error de conexión (App Vendedor)
- `MOBILE_API_MISSING_TOKEN`: la app intentó llamar API sin JWT/token activo.
- `MOBILE_API_NETWORK_FETCH_FAILED`: la PWA/App no pudo ejecutar `fetch`.
- `MOBILE_API_HTTP_<status>`: Vercel/backend respondió con HTTP no exitoso.
- `MOBILE_API_ERROR_BODY_NOT_JSON`: el servidor devolvió error no JSON.

### Códigos de error Proxy Vercel
- `PROXY_BACKEND_FETCH_FAILED`: la función serverless no pudo conectar con el backend.
- `PROXY_BACKEND_TIMEOUT`: el backend no respondió antes del timeout de 25 segundos.
