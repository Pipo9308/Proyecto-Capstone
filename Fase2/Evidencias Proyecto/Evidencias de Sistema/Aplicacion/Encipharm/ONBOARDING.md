# Encipharm — Guía de Traspaso

Bienvenido/a. Este documento te da el contexto para tomar el proyecto sin partir de cero. Léelo completo antes de tocar código — varias cosas acá cambian el sentido de lo que vas a encontrar en el repo.

---

## 1. Contexto general

Encipharm es una suite comercial para una empresa de venta farmacéutica/veterinaria, compuesta por **dos productos** que viven en este mismo repo (ver §6 sobre la estructura de git):

- **`Enci-Ventas/`** — el CRM comercial: clientes, interacciones, oportunidades, propuestas, dashboards, forecast, gestión de usuarios/roles, y un asistente documental RAG. Incluye además una app móvil nativa para vendedores (`vendedor_app_flutter/`).
- **`Enci-Intel/`** — un servicio separado de inteligencia de mercado y vigilancia de competencia: scraping de registros SAG (autoridad regulatoria chilena) y noticias de competidores, más su propio asistente RAG.

`Enci-Ventas` consume a `Enci-Intel` como una API externa a través de un proxy interno (ver §4). Son dos backends, dos frontends y dos bases de datos distintas — no un monolito.

**Cómo llegamos hasta acá:** el proyecto no partió con nosotros. `Enci-Ventas/docs/legacy-future-phases.md` y `Enci-Ventas/PENDING_FEATURES.md` documentan que nació del trabajo de otro equipo con un alcance tipo MVP. Buena parte de la interfaz se construyó como maqueta visual para iteraciones futuras, sin lógica real detrás. El 20–30 de julio de 2026 se hizo una auditoría técnica completa de ambos repos para separar "lo que parece terminado" de "lo que realmente funciona". Después de esa auditoría se empezó a trabajar en varios de los hallazgos; ese trabajo ya está commiteado en este repo (§4 y §5 detallan qué se cerró y qué no).

**Aviso importante:** `Enci-Ventas/docs/architecture.md` describe casi todos los módulos como *"Cerrado para Development"*. Esa tabla es del equipo anterior y es optimista — la auditoría encontró mocks activos en varios de esos módulos "cerrados" (Inteligencia de Mercado, Análisis de Competencia, alta de usuarios, RAG). Úsala para entender convenciones e intención de diseño, no para saber qué funciona hoy de verdad.

## 2. Qué hace (funcional hoy)

- **CRM de clientes** (Enci-Ventas): alta, listado, búsqueda, filtros, paginación, detalle, edición y baja lógica, más importación CSV administrada.
- **Pipeline comercial**: interacciones, oportunidades, propuestas con cálculo server-side, dashboards por vendedor/supervisor/admin, proyecciones y forecast exportable a CSV.
- **Autenticación y roles**: JWT propio (bcrypt), roles `vendedor` / `supervisor` / `admin` / `sin_acceso`, con separación de acceso `webApp` vs `appMovil`.
- **Gestión de usuarios**: alta, edición, cambio de rol/estado — el flujo de "agregar usuario" que antes estaba bloqueado ya tiene endpoint (`POST /users`) y frontend funcionando (ver §4).
- **App Vendedor (Flutter)**: login, cotizaciones, pipeline, forecast, consulta al RAG. Corre contra el backend real (ya no usa `demo_store.dart`, que quedó reducido a un comentario — bórralo cuando toques ese módulo).
- **Asistente RAG de Enci-Ventas**: chat sobre documentos propios, historial de conversaciones, upload/reindexado (`pgvector` sobre PostgreSQL), restringido a admin.
- **Enci-Intel — agentes de scraping**: dos agentes (`agent-sag`, `agent-competidores`) que corren como procesos independientes y ahora escriben en la misma MongoDB que lee la API (antes escribían en Firestore, que nadie leía — ver §4).
- **Enci-Intel — asistente RAG propio**: motor de embeddings + LLM sobre documentos propios, separado del RAG de Enci-Ventas.
- **Integración Enci-Ventas ↔ Enci-Intel**: existe un proxy backend (`Enci-Ventas/Backend/app/api/inteligencia.py` + `services/enci_intel.py`) que traduce entre los dos esquemas de datos y alimenta las vistas de Inteligencia de Mercado y Análisis de Competencia del CRM con datos reales en vez de arrays hardcodeados — **construido pero no verificado de punta a punta** (§5).

## 3. Qué no hace (o hace solo a medias)

- **Notificaciones, calendario y búsqueda global**: nunca tuvieron lógica real. Antes mostraban un modal "No operativo."; en el WIP actual los botones quedaron sin ningún feedback visible al usuario (ver §5 — es una regresión de UX a decidir, no un fix completo).
- **Motor de recomendaciones de productos** (`Enci-Intel/Backend/app/api/products.py: get_recommendations`): sigue siendo un stub fijo `{"encipharm": [], "competencia": []}`.
- **Scraping de competencia**: solo cubre un competidor (Drag Pharma). No hay lógica para Zoetis, Agrovet, MSD, Elanco, etc.
- **RAG (ambos)**: no debe presentarse como IA de producción con SLA. Depende de que exista un corpus documental real validado por el cliente; sin eso, responde sobre poco o nada.
- **Seguridad — dos huecos identificados que siguen sin cerrar** (ver §4 y §5): el secreto JWT y la URI de Mongo de Enci-Intel siguen con valores por defecto inseguros como fallback.
- **Fuera de alcance explícito** (`Enci-Ventas/README.md`, sección "Exclusiones"): ERP SAP, Google Calendar operativo, WhatsApp productivo, mapas/geolocalización avanzada, OCR y firma digital, BI extendido, offline total, publicación en Play Store/App Store, fine-tuning o evaluación masiva del proveedor de IA.
- **Despliegue productivo en Azure** (Fase 5 del roadmap, `Reporte_Auditoria_y_Estimacion_Enci.md`): no iniciado.

## 4. Cómo lo hace (arquitectura técnica)

### Enci-Ventas

- **Backend**: FastAPI + SQLAlchemy sobre **PostgreSQL** (migrado desde un esquema anterior — ver `docs/legacy-future-phases.md`). Auth con JWT propio (bcrypt), no Firebase.
- **Frontend**: React 19 + Vite, desplegado en Vercel.
- **App móvil**: Flutter nativo (`vendedor_app_flutter/`), consume el mismo backend vía `dio`. La URL del backend ya no está hardcodeada a una IP de LAN — usa `String.fromEnvironment('API_URL', ...)`.
- **RAG**: DeepSeek como LLM, `pgvector` como store vectorial, Azurite/GCS para documentos según entorno.
- **Rate limiting**: migrado de un middleware en memoria (no escalable) a `slowapi` + Redis (nuevo servicio en `docker-compose.yml`).
- **Proxy de inteligencia**: `app/api/inteligencia.py` traduce entre el contrato que espera el frontend de Enci-Ventas (`{source, date, title, body, tags}`, `{pregunta, conversacion_id}`, etc.) y el contrato real de Enci-Intel (`{empresa, titulo, resumen}`, `{question, species, history}`, etc.). Depende de `ENCI_INTEL_API_URL` / `ENCI_INTEL_API_KEY`.

### Enci-Intel

- **Backend**: FastAPI + **MongoDB** (Motor/AsyncIOMotorClient) + JWT propio (bcrypt) — **no Firebase, no Firestore**. `Backend/ARCHITECTURE.md` describe la versión anterior de este sistema (Firestore, Firebase Auth, Groq, Cloud Run/Scheduler/GCP) — esa migración ya ocurrió en el código pero el diagrama nunca se actualizó. No lo uses como fuente de verdad de la arquitectura actual; sí sirve para entender por qué aparecen nombres de colecciones/variables heredados de esa era.
- **Agentes de scraping**: procesos independientes (`agent-sag`, `agent-competidores`) que ahora usan `mongo_session.py` (nuevo) para escribir en la misma Mongo que lee la API, reemplazando el cliente de Firestore que dejaba los datos scrapeados invisibles para el resto del sistema.
- **Orquestación de agentes**: nuevo `app/scheduler.py` con **APScheduler** + `subprocess.Popen` reemplaza el mock que solo simulaba una respuesta exitosa al botón "Ejecutar ahora".
- **RAG**: migrado de un vector store en `pickle`/memoria a **Qdrant** real (`qdrant-client`); el loop bloqueante y las violaciones de event loop de `engine.py` también se corrigieron (async correcto, reintentos acotados en vez de `while True`).
- **Cache y rate limiting**: migrados de estructuras en memoria (no compartidas entre réplicas) a **Redis**.

### Cómo levantar el ambiente local

- **Enci-Ventas**: sigue `Enci-Ventas/README.md` y `Enci-Ventas/docs/setup.md` (comandos exactos, variables de entorno, troubleshooting de errores de conexión). Con el estado actual del código vas a necesitar además Redis corriendo (ya está en `docker-compose.yml`).
- **Enci-Intel**: no tiene un `docs/setup.md` equivalente, solo un README con la convención de branching/commits del equipo anterior. Vas a necesitar levantar **MongoDB, Redis y Qdrant** para que arranque sin errores — revisa `Enci-Intel/Backend/.env.example` para la lista completa de variables.
- Hay un `docker-compose.yml` en la raíz que incluye (`include:`) el compose de ambos repos y ya corre los dos stacks juntos con un solo `docker compose up -d --build` desde `Encipharm/` — los servicios de Enci-Intel llevan el prefijo `intel-` (`intel-db`, `intel-azurite`, `intel-backend`, `intel-frontend`) precisamente para no chocar de nombre ni de puerto con los de Enci-Ventas cuando ambos corren a la vez. Puertos publicados: Enci-Ventas en 5433/10000-10002/6379/8000/5173 (los de siempre), Enci-Intel en 27017/10010-10012/8080/5174.
- Si además tienes otro proyecto corriendo en esta máquina que ya use alguno de esos puertos (Postgres/Redis/5173/8080 son comunes), vas a necesitar bajarlo o cambiar sus puertos — eso no lo resuelve este compose, solo evita que Enci-Intel y Enci-Ventas choquen **entre sí**.
- Encontré y corregí 3 bugs que impedían levantar esto la primera vez que lo intenté (ya commiteados/commiteables junto con el resto del WIP): (1) `Enci-Intel/Backend/app/rag/engine.py` y `store.py` usaban un modelo de embeddings (`intfloat/multilingual-e5-small`) que `fastembed` no soporta — lo cambié a `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (mismas 384 dimensiones que ya espera Qdrant); (2) `Enci-Ventas/Backend/requirements.txt` tenía `redis`/`slowapi` agregados, pero el Dockerfile instala con `uv` desde `pyproject.toml`/`uv.lock`, que nunca se actualizó — lo agregué ahí con `uv add`; (3) el login de Enci-Intel fallaba con cualquier password por una incompatibilidad conocida entre `passlib` y versiones nuevas de `bcrypt` — lo resolví igual que ya estaba resuelto en Enci-Ventas, hasheando con `bcrypt` directo.

## 5. Qué falta / qué queda a medias (con evidencia archivo:línea)

Esto no es una lista de deseos — es el resultado de cruzar la auditoría de julio contra el código real que ya está commiteado.

| Ítem | Estado |
| --- | --- |
| Secreto JWT de Enci-Intel con default inseguro | **Sin tocar** — `Enci-Intel/Backend/app/api/auth.py:11`, fallback `"change_this_to_a_secure_random_key"`. Exigir la variable de entorno sin default antes de cualquier despliegue. |
| URI de Mongo de Enci-Intel con default inseguro | **Sin tocar** — `Enci-Intel/Backend/app/db.py:4`, fallback a `localhost:27017` sin exigir credenciales/TLS. |
| Scraping limitado a un solo competidor | **Sin tocar** — `Enci-Intel/Backend/agents/agent-competidores/scraper.py` sigue apuntando solo a Drag Pharma. |
| Motor de recomendaciones | **Sin tocar** — stub fijo, sin lógica de cruce de datos. |
| `market.py` / `products.py` de Enci-Intel | **Parcial** — ya consultan MongoDB en vez de devolver arrays fijos, pero las colecciones (`market_share`, `import_trends`, `positioning_matrix`, `products`) dependen de que los agentes corran y las pueblen; hoy probablemente están vacías o casi vacías. |
| Integración Enci-Ventas ↔ Enci-Intel (proxy + traducción de esquemas) | **Construida, no probada de punta a punta.** Necesitas ambos backends corriendo simultáneamente con `ENCI_INTEL_API_URL`/`ENCI_INTEL_API_KEY` configurados en Enci-Ventas, y confirmar que Enci-Intel tiene el lado M2M (CORS + auth de servicio a servicio) habilitado para aceptar al proxy — la auditoría original no documentaba que ese lado existiera todavía. |
| Notificaciones / calendario / búsqueda global | **Regresó a un estado peor que antes.** En `Enci-Ventas/frontend/src/components/AppShell.jsx` los botones ya no muestran ningún modal ni feedback — solo hacen `console.log(...)`. Antes al menos el usuario sabía que la función no estaba disponible. Hay que decidir: ¿se implementan de verdad, o se vuelve a poner feedback visual claro mientras tanto? |
| Cobertura de tests | **Brecha real en ambos repos.** Enci-Intel casi no tiene tests de agentes/scrapers/RAG; Enci-Ventas no tiene tests para varias páginas principales ni E2E. La integración nueva (proxy) no tiene tests todavía. |
| Despliegue en Azure (Fase 5 del roadmap) | **No iniciado.** |

## 6. Sobre la estructura de git (cambio reciente)

Antes del traspaso, `Enci-Intel` y `Enci-Ventas` eran **dos repositorios git independientes**, cada uno con su propio historial y remoto (`github.com/rodrigotapia-allx/Enci-Intel` y `.../Enci-Ventas`). Eso se reestructuró para simplificar el traspaso:

- Ambos dejaron de tener su propio `.git` — ahora son subcarpetas normales.
- **`Encipharm/` (esta raíz) es ahora el único repositorio git**, con remoto `https://github.com/ALLOXENTRIC-GIT/Encipharm.git`.
- El historial previo de cada proyecto no se perdió — sigue disponible en los repos originales de GitHub (arriba) por si alguna vez hace falta consultarlo; el monorepo arrancó con un commit inicial limpio que incluye el estado actual de ambos.
- Este documento (`ONBOARDING.md`) sí queda trackeado y va con el push, precisamente para que lo tengas apenas clones el repo.

## 7. Datos de prueba (seed) — importante al clonar de cero

Al clonar este repo **las bases de datos están vacías**. Nada de lo que se ve en una demo (clientes, oportunidades, datos de mercado, etc.) viene incluido en el repo ni se genera solo al levantar los contenedores — hay que sembrarlo explícitamente, cada vez que se levanta un ambiente nuevo:

- **Enci-Ventas** (Postgres): correr, con el backend arriba,
  - `uv run python scripts/seed_admin.py` → crea `admin@enci.cl` / `admin123` (rol admin).
  - `PYTHONPATH=. uv run python scripts/seed_max_wellq_demo.py --apply` → crea `vendedor.demo@enci.cl` / `password123` con clientes, oportunidades y propuestas de ejemplo ya cargados. Ambos scripts están en `Enci-Ventas/Backend/scripts/` y son idempotentes (se pueden correr de nuevo sin duplicar datos).
- **Enci-Intel** (MongoDB): no traía ningún seed — lo agregué en `Enci-Intel/Backend/scripts/seed_demo_data.py`. Corre `python scripts/seed_demo_data.py --apply` con el backend arriba para poblar `market_share`, `positioning_matrix`, `import_trends` y `products` con datos de ejemplo (lo que en producción deberían llenar los agentes de scraping, que hoy solo cubren un competidor real — ver §5). Sin esto, las pestañas de Inteligencia de Mercado y Análisis de Competencia se ven vacías aunque todo el resto funcione bien.

## 8. Recomendaciones — próximos pasos en orden sugerido

1. **Revisa y prueba lo que ya está commiteado en el WIP de la auditoría** (§5): no partas de cero, gran parte de las Fases 2 y 3 del roadmap original ya tiene código escrito — falta principalmente probarlo (Redis, Qdrant y Mongo corriendo localmente) y cerrar los dos ítems de seguridad que quedaron sin tocar.
2. **Prueba de punta a punta la integración Enci-Ventas ↔ Enci-Intel** — es la pieza más grande construida y la menos verificada; sin esto la pestaña de Inteligencia del CRM puede fallar en silencio o mostrar datos vacíos aunque el código "compile".
3. **Decide conscientemente sobre notificaciones/calendario/búsqueda** en `AppShell.jsx` — no lo dejes en el estado silencioso a medias en el que quedó.
4. **Revisa con quien traspasa un puñado de archivos sueltos en `Enci-Ventas/` que no pertenecen a este proyecto** (`mongo_script.js`, `queries_remote.py`, `weaviate_*`) — referencian datos de otro cliente, ya están excluidos del tracking pero conviene confirmar si se pueden borrar del disco directamente.
5. **Retoma el roadmap desde donde quedó**: lo más grande que falta completo es la Fase 4 (motor real de scraping multi-competidor, notificaciones, búsqueda global) y la Fase 5 (despliegue productivo en Azure) de `Reporte_Auditoria_y_Estimacion_Enci.md`.
