# Enci Ventas / MiniCRM Comercial

## Descripcion

Enci Ventas centraliza la gestion de clientes, usuarios, roles, interacciones, oportunidades, propuestas, dashboards comerciales, importacion CSV y asistencia documental RAG en una arquitectura web con backend FastAPI, frontend React/Vite, y base de datos relacional PostgreSQL con autenticación JWT nativa.

El repositorio queda preparado para entrega tecnica, UAT y go-live condicionado por credenciales, dominios y validacion final del cliente.

## Alcance entregado

- MVP web comercial con login tradicional protegido mediante tokens JWT.
- API FastAPI con base de datos PostgreSQL (via SQLAlchemy) para persistencia.
- Roles `vendedor`, `supervisor`, `admin` y estado `sin_acceso`.
- Bloqueo de usuarios inactivos y control de acceso por `webApp`/`appMovil`.
- CRM de clientes conectado a backend PostgreSQL.
- Creacion, listado, busqueda, filtros, paginacion, detalle, edicion y baja logica de clientes.
- Importacion CSV administrada con validaciones defensivas.
- Interacciones, oportunidades, propuestas y detalle comercial.
- Dashboard vendedor y dashboard supervisor/admin.
- Forecast, proyecciones y exportacion CSV.
- Administracion de usuarios, roles, estado, tema e idioma.
- Asistente Enci RAG parcialmente entregado, con endpoints backend, historial, documentos e indexacion.
- App Vendedor oficial en Flutter dentro del repositorio (`vendedor_app_flutter`).
- Readiness, hardening, QA tecnica y documentacion de cierre.

## Componentes del repositorio

```text
/
|-- Backend/              # API FastAPI, routers, modelos (SQLAlchemy), servicios, tests y config
|-- frontend/             # CRM web React/Vite
|-- vendedor_app_flutter/ # App Vendedor móvil nativa (Flutter)
|-- docs/                 # Documentacion tecnica, QA, API, deploy, y evidencia historica del proyecto
|-- tools/                # Scripts de smoke test y E2E
|-- docker-compose.yml    # Infraestructura local (PostgreSQL, Azurite)
|-- README.md
```

### Sobre la carpeta `docs/`

La carpeta `docs/` ha sido refactorizada para enfocarse estrictamente en el estado actual del desarrollo, eliminando los documentos legados:
- **`architecture.md`**: Diagramas, stack tecnológico y flujo de la plataforma.
- **`setup.md`**: Guía técnica para levantar la plataforma localmente y troubleshooting.
- **`api-reference.md`**: Referencia de los contratos y endpoints de la API (usando autenticación JWT).
- **`legacy-future-phases.md`**: Historial de fases futuras, exclusiones y features descartadas provenientes del MVP inicial.

## Estado de IA RAG

El RAG esta parcialmente entregado y preparado para validacion controlada. No debe presentarse como plataforma IA completa, producto con SLA definitivo, fine-tuning o evaluacion masiva.

Incluye:

- `POST /rag/chat`
- `GET /rag/conversations`
- `POST /rag/documents/upload`
- `POST /rag/documents/reindex`
- `GET /rag/documents`
- DeepSeek consumido solo desde backend.
- Base de datos vectorial utilizando PostgreSQL (pgvector).
- GCS o almacenamiento local para documentos segun variables.
- Historial de conversaciones por usuario.
- Upload, reindex y listado documental restringidos a `admin`.

Condiciones:

- Requiere `DEEPSEEK_API_KEY` real para ambiente desplegado.
- Requiere corpus documental definitivo validado por el cliente.

## Estado de App Vendedor / Flutter

La aplicación móvil nativa oficial se encuentra en la carpeta `vendedor_app_flutter/`. Se ha descartado la versión web progresiva (PWA) para consolidar el desarrollo móvil en Flutter.

## Arquitectura Actualizada

- Frontend web React/Vite en Vercel.
- App móvil nativa Flutter para vendedores.
- Backend FastAPI con PostgreSQL (datos relacionales y pgvector).
- Autenticación implementada localmente mediante **JWT (JSON Web Tokens)** con contraseñas encriptadas con `bcrypt`.
- RAG backend con DeepSeek, pgvector y almacenamiento documental configurable (usando Azurite/Blob Storage).

```mermaid
graph TD
    ClientWeb[Frontend Web React] -->|HTTPS / REST| API[Backend FastAPI]
    ClientMobile[App Móvil Flutter] -->|HTTPS / REST| API
    
    API -->|Auth| JWT[Validación JWT local]
    API -->|SQL| DB[(PostgreSQL)]
    API -->|Vector Search| PGVector[(pgvector)]
    API -->|LLM Prompts| LLM[DeepSeek API]
    API -->|Documentos RAG| Storage[Azurite / GCS]
    
    DB --- PGVector
```

El frontend y la app móvil consumen datos de negocio a traves del backend. Todas las contraseñas y secretos deben manejarse mediante variables de entorno en el despliegue.

## Instalacion local

Inicio rapido en Windows:

```powershell
.\iniciar-enci-local.bat
```

Backend:

```bash
cd Backend
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend web:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

App Vendedor (Flutter):

```bash
cd vendedor_app_flutter
flutter pub get
flutter run
```

Backend:

```env
APP_NAME=Enci Ventas API
APP_ENV=development
APP_VERSION=1.0.0
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173","http://localhost:5174","http://127.0.0.1:5173","http://127.0.0.1:5174"]
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/enci_db
SECRET_KEY=tu-clave-secreta-jwt
DEEPSEEK_API_KEY=your_deepseek_api_key_here
GCS_BUCKET_DOCUMENTS=
LOCAL_DOCUMENT_STORAGE_DIR=./document_storage
```

Frontend web (`.env`):

```env
VITE_APP_NAME=Enci Ventas
VITE_API_BASE_URL=http://localhost:8000
```

Los placeholders anteriores son ejemplos documentales. No se deben versionar `.env`, ni secretos de JWT o Base de datos.

## QA y validacion

Comandos esperados:

```bash
cd Backend
uv sync
uv run pytest
```

```bash
cd frontend
npm ci
npm run lint
npm run build
```

```bash
cd vendedor_app_flutter
flutter analyze
flutter test
```

Smoke test de ambiente publicado:

```bash
python tools/smoke_crm_web.py --env uat --api-base-url https://api.example.com --web-url https://crm.example.com
```

Con token real:

```bash
python tools/smoke_crm_web.py --env uat --api-base-url https://api.example.com --web-url https://crm.example.com --token <firebase_id_token>
```

## Despliegue

- Frontend web: Vercel, con `frontend/` como proyecto o build configurado desde la raiz.
- App Vendedor (Flutter): Compilada localmente para dispositivos móviles.
- Backend: Docker / Infraestructura interna apuntando a PostgreSQL.
- Base de Datos: PostgreSQL.
- CORS: configurar solo origenes reales del ambiente.
- Swagger/OpenAPI: `/openapi.json` queda deshabilitado en `APP_ENV=production`.
- `/docs`: consola de pruebas propia del backend; no debe exponerse como superficie productiva publica sin control de ambiente.

## Exclusiones

Quedan fuera del alcance cerrado de este repositorio salvo evidencia futura:

- ERP SAP.
- Google Calendar operativo.
- WhatsApp productivo.
- Mapas/geolocalizacion avanzada.
- OCR y firma digital.
- BI extendido.
- Offline total.
- Publicacion Play Store/App Store.
- Fine-tuning, evaluacion masiva o SLA productivo del proveedor IA.
- App Flutter nativa dentro del repositorio.



