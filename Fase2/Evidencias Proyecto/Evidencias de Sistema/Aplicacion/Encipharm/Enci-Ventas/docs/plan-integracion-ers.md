# Plan de integración — ERS "Encipharm Ventas · Inteligencia de Mercado" v1.0

Base: `ERS_Encipharm_Ventas_Inteligencia_de_Mercado_v1.pdf` (29-09-2026, PO Max Kreimerman), las dos capturas de WhatsApp (tabla de brechas y nota de scrapers con Playwright) y el análisis del código del 2026-10-12 (commit `236576e`).
Estado: borrador para revisión. Nada de esto está implementado todavía.

---

## 1. Hallazgo principal: el ERS describe otro stack

El ERS asume **Firebase Auth + Firestore + Cloud Run + Vue 3/Vuetify + Gemini/Vertex**. El repositorio real usa **JWT propio + Postgres (Ventas) / MongoDB (Intel) + Render + React + NVIDIA NIM/DeepSeek**. El propio ERS (§2) pide verificar cada punto contra la rama real. Este plan **adapta cada requerimiento al stack actual**; los nombres de colecciones de Firestore pasan a tablas Alembic.

### Hallazgos H-01…H-11 contra el código real

| ERS | Veredicto | Realidad |
|---|---|---|
| H-01 Flutter con una sola URL, sin Intel | **Cierto** | `API_URL` por `--dart-define` (default `10.0.2.2:8000`); sin pantallas de alertas ni competencia. |
| H-02 Dos proyectos Firebase | **No aplica** | No hay Firebase. Cada backend tiene su JWT con secreto distinto; un token de Ventas no sirve en Intel. Hoy se resuelve con `X-API-Key` servicio-a-servicio. |
| H-03 Intel sin login en `/alerts`, `/dashboard`, `/products`, `/market` | **Desactualizado** | Cerrado en el commit `4661ab5`. Pendiente: `/products` y `/market` siguen devolviendo datos demo, y la API key de servicio **solo** vale en `/market/*` y `/chat/*` (no en `/alerts`). |
| H-04 Consultor Veterinario rechaza temas comerciales | **Cierto** | `engine.py` (`_RULES`, `_COMMERCIAL_RE`). Hay que hacer un asistente nuevo, no reutilizar este. |
| H-05 Intel tiene datos reales | **Cierto** | `alerts`, `sag_productos`, `competitor_news` (solo Drag Pharma). Las alertas **no tienen un campo "competidor"**: viene en `data.empresa` / `Importador o Registrante`. |
| H-06 Asistente CRM con Gemini 1.5 y sin fuentes | **Desactualizado** | Ventas ya usa DeepSeek/NIM con RAG real y fuentes. |
| H-07 Crear usuario no crea cuenta | **Parcial** | `POST /users` ya crea usuario **con contraseña fijada por el admin**. Falta invitación por email y reseteo. `/auth/register` público crea filas `sin_acceso`. No hay duplicados de ID (UUID en Postgres) ni Google SSO. |
| H-08 Crear clientes falla (`VITE_API_URL`, Vuetify) | **No aplica** | La web es React. Causa real: las rutas `/clientes`, `/crear` existen pero **no hay enlace en el menú**; además el modelo **no tiene RUT**. |
| H-09 Competencia solo CRUD, pisa precios | **Peor** | `services/competencia.py` es un stub; `GET /competencia/repository` devuelve listas vacías. |
| H-10 Sin notificaciones ni calendario | **Cierto** | `AppShell.jsx` solo hace `console.log`; el punto rojo es fijo. |
| H-11 RAG en disco efímero; sin adjuntos en propuestas | **Parcial** | Índice en pgvector/Qdrant (persistente) y archivos en Azure Blob. Pero la **subida está rota** (ver Fase 0) y no hay adjuntos de propuesta. |

Las capturas confirman la tabla de brechas del ERS (RQ-09 y RQ-08 no existen; RQ-04 solo lectura; RQ-07 mitad PDF; RQ-01/02 solo maqueta) y añaden un punto fuera del ERS: **scrapers de Agrovet y Zoetis con Playwright** (hoy descartado por frágil). Ver Fase 4, ítem 4.6.

---

## 2. Decisiones abiertas (bloquean o cambian el diseño)

| # | Decisión | Recomendación | Bloquea |
|---|---|---|---|
| D1 | ¿Se adapta el ERS al stack real (JWT/Postgres/React/Render)? | Sí. Confirmar con el PO. | Todo |
| D2 | Búsqueda web en vivo: el ERS sugiere Gemini/Vertex; el repo no usa GCP | Un proveedor de búsqueda por API (Tavily, Brave o SerpAPI) llamado como herramienta del modelo | Fase 2 |
| D3 | Modelo con *function calling* fiable. DeepSeek no tiene saldo; Llama 3.2-11B (NIM) es débil en herramientas | Elegir y probar un modelo antes de diseñar el chat | Fase 2 |
| D4 | Proveedor de email para invitaciones (no hay SMTP) | Resend/SendGrid/SMTP; necesita dominio y remitente | Fase 3 (RQ-05) |
| D5 | **Catálogo de productos Encipharm**: no existe ninguna tabla (`products` de Intel es demo). Hace falta para "equivalentes" y comparativas | Que el PO entregue el catálogo (CSV) o definir su alta en Ventas | Fases 1 (ficha) y 4 |
| D6 | Hosting: Render free (512 MB, duerme a los ~15 min, cron en proceso) | Subir de plan antes de comprometer p95 < 2 s y avisos de 60 s; Playwright no cabe en 512 MB | Fases 1, 4 |
| D7 | RNF-11 pide `/api/v1`; Ventas no tiene prefijo | No cambiarlo ahora (rompe web y Flutter); añadir alias `/api/v1` al final | Fase 5 |
| D8 | Campos obligatorios de cliente (RUT, industria) | Confirmar con el PO; hoy no hay RUT | Fase 3 (RQ-06) |
| D9 | Vocabulario de roles de Intel (`admin/administrador/Admin`) | Un único valor canónico normalizado en backend | Fase 0 |

Hasta que se resuelvan, el plan avanza con las recomendaciones.

### Decisiones tomadas (2026-10-12, sin consultar al PO por ahora)

Se adoptan las recomendaciones de la tabla y estos matices, sujetos a confirmación posterior con el PO:
D1 adaptar el ERS al stack real · D2 búsqueda web tras un interruptor, al final de la Fase 2 · D3 DeepSeek configurable por variable de entorno, con prueba previa de *function calling* · D4 invitación con enlace copiable por el admin (email después) · D5 tabla mínima `productos_encipharm` con importación CSV · D6 sin subir plan de hosting ni scrapers con Playwright · D7 sin prefijo `/api/v1` en Ventas · D8 obligatorios nombre, empresa, RUT y rubro (RUT nullable en datos existentes) · D9 roles de Intel canónicos `admin/gerencia/comercial/pendiente`, con normalización de valores históricos.

### Avance de la Fase 0 (rama `fase-0-bloqueantes`)

| Tarea | Estado | Verificación |
|---|---|---|
| 0.1 `token`→`idToken` en Inteligencia/Competencia | Hecho | Lectura de código; vitest de Ventas pasa (36) |
| 0.2 Respuestas 204 en `apiFetch` | Hecho | 3 tests nuevos (vitest) |
| 0.3 Formulario de subida (`currentTarget` tras `await`) | Hecho | Lectura de código |
| 0.4 Orden de inserción en la subida RAG de Ventas + `AZURE_STORAGE_CONNECTION_STRING` en el compose | Hecho | 2 tests nuevos (`test_rag_upload_order.py`), **sin ejecutar** (ver nota) |
| 0.5 Intel: `uid`→`sub` en la subida y conteo de documentos | Hecho | Tests nuevos (`test_roles_and_docs.py`), **sin ejecutar** |
| 0.6 Roles de Intel (D9) | Hecho | Tests de backend **sin ejecutar**; 3 tests de frontend pasan |
| 0.7 Login fallido de Intel ya no recarga la página | Hecho | 2 tests nuevos (node) pasan; `tsc` + `vite build` OK |
| 0.8 Enlaces de menú a Clientes, Nuevo cliente, Interacciones y Propuestas | Hecho | Lectura de código |
| 0.9 Flutter: permiso `INTERNET` y error de login | Hecho (parcial) | Sin SDK de Flutter: no compilado. `pubspec.lock` sigue sin regenerar |
| 0.10 Migraciones automáticas y Postgres con healthcheck en el compose | Hecho | **Sin probar**: Docker no responde en esta máquina |
| 0.11 Serializadores que descartaban campos | Hecho | 3 tests nuevos, **sin ejecutar** |
| 0.12 CI con Postgres y lint | Pendiente | Se difiere a la Fase 5 |

Estado tras reiniciar Docker: el compose aplica las migraciones al arrancar (comprobado en Postgres) y los tests de Python pasan dentro de Docker (Ventas 135, Intel 136). El test de la subida RAG falla con el código antiguo y pasa con el arreglo. `pubspec.lock` regenerado y Flutter verificado en un contenedor (38 tests, 0 errores de análisis).

### Avance de la Fase 1 (RQ-09)

| Tarea | Estado | Verificación |
|---|---|---|
| 1.1 Permiso "Acceso a Inteligencia" (columna + migración, API de usuarios, 403 en `/inteligencia/*`, casilla en Configuración, menú y ruta condicionados; el admin siempre accede) | Hecho | 11 tests de backend, 5 de frontend |
| 1.2 Intel: `/alerts` acepta la API key de servicio, filtros (`priority`, `type`, `competitor`), paginación (`limit`/`offset`, tope de 200), campo `competitor`, detalle `/alerts/{id}`, fechas con zona UTC | Hecho | 14 tests de backend |
| 1.3 Intel: `GET /sag/productos?q=` y `/sag/productos/{registro}` sobre `sag_productos` (nombre, principio activo, titular, registro) con alertas relacionadas | Hecho | 14 tests de backend |
| 1.4 Ventas: tabla `intel_lecturas` y contador de no leídas (sobre las 200 alertas más recientes) | Hecho | tests de backend + prueba real contra Postgres |
| 1.5 Ventas: ficha de producto con origen y fecha por dato; `precios` y `equivalente_encipharm` vacíos hasta RQ-04 y el catálogo (D5) | Hecho | tests de backend |
| 1.6 Proxy robusto: timeouts, Intel caído → 503 con mensaje, 401/403/5xx de Intel → 502 (no cierra la sesión del usuario) | Hecho | tests de backend |
| 1.7 Flutter: pestaña Inteligencia (feed con filtros, scroll infinito, tirar para refrescar, detalle, buscador y ficha), contador de no leídas, copia local de 100 alertas y fichas de 7 días con aviso "datos del dd/mm a las hh:mm", guardia de release contra localhost/HTTP | Hecho | 38 tests de Flutter |
| 1.8 Prueba de punta a punta Ventas → Intel real (Postgres + Mongo + API key) | Hecho | alertas, marcar leída, contador, búsqueda y ficha respondieron bien |

### Avance de la Fase 2 (RQ-08)

| Tarea | Estado | Verificación |
|---|---|---|
| 2.1 Modelo configurable por variable de entorno (`COMPETENCIA_MODEL`, por defecto `DEEPSEEK_MODEL`) y cliente compatible con OpenAI | Hecho; **prueba real de function calling pendiente** (no hay `DEEPSEEK_API_KEY`) | 6 tests contra un servidor local compatible con OpenAI usando el SDK real |
| 2.2 Herramientas acotadas: `buscar_alertas`, `buscar_producto_sag`, `noticias_competidor`, `precios_competencia` (vacía hasta RQ-04) + `buscar_web`; prompt propio que sí habla de precios, ignora instrucciones de la web, no usa datos del CRM | Hecho | 35 tests con modelo, Intel y web falsos |
| 2.3 Respuesta por eventos SSE (`estado`, `fuentes`, `texto`, `fin`/`error`) | Hecho, con una salvedad: el texto se parte en trozos **después** de que el modelo responde (las rondas de herramientas no son streaming) | tests de backend y de Flutter (parser con trozos partidos en cualquier byte) |
| 2.4 Conversaciones por usuario, 👍/👎, tope diario por usuario en Ventas (`COMPETENCIA_CHAT_DAILY_LIMIT`, 50), uso por día y reporte mensual para el admin con costo aproximado | Hecho | tests de backend; migración aplicada en Postgres |
| 2.5 Fuentes distinguibles (Enci-Intel vs Internet) | Hecho | tests de backend y de widgets |
| 2.6 Flutter: pestaña "Competencia IA" dentro de Inteligencia (ejemplos, streaming, fuentes, historial, feedback, tope, lectura sin conexión del historial guardado) | Hecho | 65 tests de Flutter en total |
| 2.7 Búsqueda web (Tavily) | Hecho, **apagada por defecto** (`WEB_SEARCH_ENABLED=false`); sin datos personales en la consulta y resultados marcados como no confiables | tests con transporte simulado; **no probada contra la API real de Tavily** |

Pendiente de la Fase 2: probar con un modelo real (qué modelo soporta *function calling* de forma fiable), activar la búsqueda web con clave real, medir los tiempos (3 s al primer texto, 15 s al final) y usar el mismo chat en la web de Ventas (RQ-03, Fase 4). La cuota se cuenta por intento: una pregunta que falla en el modelo también cuenta.

### Avance de la Fase 3 (RQ-05, RQ-06, RQ-07)

| Tarea | Estado | Verificación |
|---|---|---|
| **RQ-06** RUT obligatorio y único (formato canónico `12345678-5`, dígito verificador, índice único parcial que ignora clientes dados de baja); campos requeridos iguales en backend y web (contacto, empresa, RUT, rubro; email, teléfono y región opcionales); `409` que dice cuál cliente tiene ese RUT y quién lo tiene asignado; errores `422`/`409` mostrados en el campo; supervisor y admin pueden asignar/reasignar vendedor (selector en la web); asignar a un usuario inexistente es un `422` claro y no un `500`; CSV exige RUT y rubro y reporta duplicados en la fila correcta | Hecho | tests de backend y web; migración y duplicados probados contra Postgres real |
| **RQ-05** Usuarios con invitación: el admin crea la cuenta sin contraseña y recibe un enlace de un solo uso válido 72 h (solo se guarda su hash); pantalla pública `/activar`; estados invitado/activo/desactivado; "¿Olvidaste tu contraseña?" en web y app (deja la solicitud visible al admin, que genera un enlace); contraseña ≥ 10 con letras y números; registro público cerrado; un login con contraseña de más de 72 bytes ya no da `500` | Hecho, **sin envío de correo** (D4) | tests de backend, web y Flutter; flujo completo probado contra el stack real |
| **RQ-07** Documentos del RAG: `202` inmediato, indexación en segundo plano con estados subido → procesando → listo/error (con el motivo), lista que se actualiza sola, borrado (sale del índice y del almacenamiento), duplicados por contenido o nombre, límite 25 MB | Hecho | tests de backend y web; probado con el modelo de embeddings real y Azurite |
| **RQ-07** PDF de propuestas: adjuntar hasta 10 PDF de 20 MB con barra de progreso, listar, borrar y descargar con **enlace firmado que vence a los 10 minutos** (dueño, supervisor y admin) | Hecho | tests de backend y web; subida, descarga sin sesión y borrado probados contra Azurite real |

No incluido todavía en la Fase 3: envío real de correos (invitación, restablecimiento), registro de auditoría de altas y cambios de rol (RF-05.10, Fase 5), alta de clientes y adjuntos desde Flutter (marcados "Importante"), y estados de indexación en los documentos del RAG de Enci-Intel (solo se corrigieron sus errores en la Fase 0). Una contraseña cambiada no invalida las sesiones ya abiertas (el token dura 7 días).

### Avance de la Fase 5

| Tarea | Estado | Verificación |
|---|---|---|
| **5.1 Auditoría** en SQL (`audit_logs`): middleware ASGI que registra quién (token), qué, recurso, estado, IP y agente de cada escritura y de las descargas de archivos, con los intentos de login (correo, nunca la contraseña); `GET /auditoria` solo admin con filtros y paginación; hora ISO 8601 con milisegundos; sin endpoints para editar o borrar; si la auditoría falla no tumba la petición | Hecho | 14 tests; migración subida/bajada/subida; registros reales vistos en el stack |
| **5.2 Seguridad:** un test recorre todas las rutas y exige sesión salvo `/health` y los endpoints de acceso a la cuenta; `/readiness` pasa a admin y `/` se elimina; `APP_ENV` por defecto `production`; el CORS no incluía `PUT` (las equivalencias de competencia fallaban en el navegador) y ahora sí; se quitó el plugin y el `google-services.json` de Firebase de la app (no usa Firebase) | Hecho, salvo rotar credenciales | 85 tests; suite completa verificada con `APP_ENV=production` |
| **5.3 CI:** lint (`ruff`, solo errores reales; se corrigieron 32 hallazgos), cobertura con piso de 80 % (hoy 91 %), job con Postgres + pgvector que sube, baja y vuelve a subir todas las migraciones y corre `alembic check` (sin diferencias con los modelos), y `npm run lint` en la web | Hecho; el workflow no se pudo ejecutar fuera de GitHub (se validó su sintaxis) | migraciones y `alembic check` probados contra Postgres local |
| **5.4 Logs:** JSON por línea con hora ISO, nivel y datos de la petición (método, ruta, estado, duración), `X-Request-ID`, y los errores 500, que antes no dejaban rastro, ahora salen con traceback y nivel ERROR | Hecho; sin métricas ni reglas de alerta en el hosting | 6 tests |
| **5.5** `/api/v1` descartado por la decisión D7; OpenAPI se genera solo; las pantallas nuevas no se tradujeron porque solo la barra lateral y Configuración usan el diccionario | Decidido | — |
| **5.6 Builds firmados** de Android/iOS | Pendiente: necesita claves de firma y entorno de producción | — |
| **5.7 Documentación:** `PENDING_FEATURES.md`, `architecture.md`, `setup.md`, `api-reference.md` y `legacy-future-phases.md` al día | Hecho | — |

Pendiente de la Fase 5: rotar las credenciales (la clave de Firebase queda en el historial de git: hay que restringirla o rotarla en la consola de Google), configurar alertas en el hosting sobre `level=ERROR`, y hacer que los tests antiguos corran sobre Postgres (usan UIDs falsos que las claves foráneas rechazan).

### Avance de la Fase 4 (RQ-04 → RQ-03 → RQ-01 → RQ-02)

| Tarea | Estado | Verificación |
|---|---|---|
| **4.1 RQ-04** Backend de competencia: tablas `productos_competencia`, `precios_competencia` (historial, nunca se pisa), `productos_encipharm` (catálogo mínimo, D5) y `equivalencias_producto`; precio por unidad (ml/g/dosis) calculado al leer; reportes de vendedor quedan *pendiente* hasta que supervisor/admin los aprueban o descartan (los de supervisor/admin se aprueban solos); lista con filtros (competidor, categoría, principio, texto) y paginación en SQL con orden estable; comparativa por producto Encipharm (diferencia % = (Encipharm − competidor) / competidor, positivo = Encipharm más caro; explica por qué no hay diferencia si faltan precio, unidad o moneda); resumen por categoría y competidor; permisos: vendedor consulta/registra/reporta, supervisor edita y aprueba, solo admin borra. La herramienta `precios_competencia` del chat y `precios`/`equivalente_encipharm` de la ficha de producto (Flutter) ya leen estos datos (solo precios aprobados; la ficha cruza por registro SAG) | Hecho en backend | 31 tests nuevos; migración subida/bajada/subida contra Postgres real; flujo completo probado con el stack real |
| **4.2 RQ-03** Inteligencia de Mercado (web) con datos reales: alertas de Enci-Intel con filtros por competidor (los de las alertas reales) y «Regulación»; chat de competencia (el de la Fase 2, sin streaming) con preguntas de ejemplo y fuentes; comparación de precios por producto Encipharm con diferencia % por unidad, comparación de composición y resumen por categoría/competidor; reportar precios (todos) y cola de aprobación + catálogo y equivalencias (supervisor/admin); cada bloque con cargando / vacío / error con reintento y hora de actualización. Se eliminó el contrato roto (`/inteligencia/competencia`, `/competencia/repository`) y los datos inventados: competidores de ejemplo (VetPharma, AgriSur…), «Presión/Defensa competitiva» y «Valor en riesgo» de la oportunidad, «Prom. industria 35%» | Hecho | 22 tests web nuevos (108 en total), lint y build limpios; backend 336 |
| **4.3 RQ-01** Notificaciones dentro de la web: tabla `notificaciones` (retención 90 días con purga horaria), `GET /notificaciones` (paginado, con contador de no leídas), marcar una o todas como leídas (cada usuario solo ve y toca las suyas); campana real en la barra superior con contador, panel, enlace a lo que corresponde y consulta cada 30 s (aparece en < 60 s). Avisos: alerta crítica/alta de Enci-Intel (a quienes tienen acceso a Inteligencia y admins; sin duplicar), propuesta que cambia de estado por obra de otro usuario (al dueño), cliente asignado o reasignado por otro (al vendedor), documento RAG listo o fallido (a los admins). **Sin planificador:** el sondeo a Intel se dispara cuando alguien consulta sus avisos (como máximo cada 120 s, mira 72 h atrás); si nadie tiene la web abierta no detecta nada hasta que alguien entre | Hecho | 17 tests de backend y 8 de web; migración subida/bajada/subida y alerta real de Intel recibida contra el stack real |
| **4.4 RQ-02** Calendario: tabla `eventos` (cliente obligatorio, oportunidad opcional del mismo cliente, tipo presencial/virtual/llamada, inicio/fin en UTC, lugar, notas, estado planificada/realizada/cancelada); un vendedor solo ve y edita los suyos, supervisor/admin ven todo el equipo con filtro por vendedor y pueden agendar para otro (le llega un aviso); «realizada» crea la interacción en el historial del cliente una sola vez; un evento realizado/cancelado ya no se mueve. Web: vistas mes/semana/día, arrastrar un evento a otro día (conserva hora y duración), crear/editar/cancelar/realizar, «Agendar visita» desde la ficha del cliente y botón del calendario en la barra superior. Avisos 24 h / 1 h por el sistema de notificaciones (se vuelven a emitir si la visita se mueve) | Hecho | 28 tests de backend y 20 de web; migración subida/bajada/subida; evento, aviso e historial probados contra el stack real |

Pendiente de 4.4: la vista semana/día es una lista por día (no una grilla por hora): se arrastra entre días y la hora se cambia en el formulario; la lista «Mis próximas visitas» de Flutter (4.5, «si da el tiempo») no se hizo; los recordatorios muestran el aviso pero no la hora (el servidor no conoce la zona del usuario).

Pendiente de 4.3: «te asignan una oportunidad» (RF-01.03) no existe como evento, porque una oportunidad siempre pertenece a quien la crea y no se puede reasignar; se cubre con la asignación de clientes (RQ-06). Faltan los avisos de visita del calendario (RQ-02), silenciar tipos de aviso (RF-01.06, «si da el tiempo») y, si se quiere detectar alertas sin que nadie tenga la web abierta, un planificador o un webhook desde Intel (D6).

Pendiente de 4.1: carga masiva por CSV/Excel de listas de precios y del catálogo (RF-04.08, "si da el tiempo"), pantalla web de reporte/aprobación (entra con 4.2), y que el PO cargue el catálogo real de Encipharm. Atajos conocidos: el resumen se agrupa en memoria (subir a SQL pasado unos miles de productos) y no hay conversión entre unidades (l→ml, kg→g).

Pendiente de la Fase 1: build de release de Android (en curso), y revisar con el PO que el modo sin conexión cubra RF-09.08 en su versión simple.

Nota: en esta máquina una política de control de aplicaciones de Windows bloquea las extensiones nativas de Python (`pydantic_core`), y Docker Desktop no responde. Los tests de Python se ejecutarán en Docker o en el CI.

---

## 3. Fases, por orden de severidad

La severidad combina la prioridad del ERS (P0/P1/P2) con lo que **hoy está roto** en el código: no se puede construir RQ-09 sobre pantallas que cierran la sesión ni sobre una subida de documentos que da 500.

### Fase 0 — Bloqueantes y base (CRÍTICA) · tamaño M

Sin esto, el resto no se puede probar. Incluye las partes triviales de RQ-05/06/07.

| # | Tarea | Dónde |
|---|---|---|
| 0.1 | Entrar a Inteligencia/Competencia cierra la sesión: usan `token`, el contexto expone `idToken` | `Enci-Ventas/frontend/src/pages/InteligenciaMercado.jsx:6`, `AnalisisCompetencia.jsx:15` |
| 0.2 | `apiFetch` rompe con respuestas 204 (borrar cliente muestra error falso) | `frontend/src/services/api.js:174` |
| 0.3 | Subida RAG muestra error falso (`currentTarget.reset()` tras `await`) | `frontend/src/components/rag/UploadDocuments.jsx:38` |
| 0.4 | Subida RAG de Ventas: los chunks se insertan antes que el documento (FK) | `Backend/app/services/rag_service.py:741-742`; pasar `AZURE_STORAGE_CONNECTION_STRING` en el compose |
| 0.5 | Subida de documentos de Intel da 500 (`uid` vs `sub`) y `/chat/docs-count` da 500 | `Enci-Intel/Backend/app/api/admin_documents.py:87`, `chat.py:84` |
| 0.6 | Roles de Intel: unificar vocabulario (cambio de rol da 400; el seed crea `admin` que el front no reconoce) | `admin_users.py:9`, `seed_admin.py`, `Frontend/src/types`, `sidebar.tsx`, `mainContent.tsx` (D9) |
| 0.7 | Un login fallido en Intel recarga la página (cualquier 401) | `Intel/Frontend/src/services/api.ts`, `session.ts` |
| 0.8 | Enlaces de menú a `/clientes`, `/crear`, `/interacciones`, `/propuestas` | `frontend/src/components/AppShell.jsx` |
| 0.9 | Flutter: permiso `INTERNET` en el manifest principal; el login lee `detail` en vez de `error`; regenerar `pubspec.lock` | `vendedor_app_flutter/android/app/src/main/AndroidManifest.xml`, `auth_service.dart:39` |
| 0.10 | Entorno reproducible: migraciones y seeds automáticos o documentados (`alembic upgrade head`), `.env` completo | `Enci-Ventas/docker-compose.yml`, `Dockerfile` |
| 0.11 | Datos de la API que se pierden en silencio (`resultado`, `proximaAccion`, `descripcion`, `notas`) | `Backend/app/services/comercial.py:28-67` |
| 0.12 | Pruebas de regresión para cada punto anterior y CI contra **Postgres+pgvector** (SQLite oculta fallos de FK) | `.github/workflows/ci.yml`, `tests/` |

**Criterio de salida:** login → Inteligencia sin cierre de sesión; subir y borrar un documento en ambos sistemas; crear un cliente desde el menú; el móvil release se conecta; todo con tests.

### Fase 1 — RQ-09: Flutter conectada a Enci-Intel (CRÍTICA, P0) · tamaño L

**Arquitectura:** Opción A del ERS (Ventas como intermediario). Ya es el patrón real: `Enci-Ventas/Backend/app/api/inteligencia.py` + `services/enci_intel.py` con `X-API-Key`. Se extiende en vez de rehacer; las rutas nuevas van bajo `/inteligencia/*` (D7).

| # | Tarea | RF |
|---|---|---|
| 1.1 | Campo `accesoInteligencia` en `users` (migración Alembic, esquemas, y las listas de claves de los serializadores), dependencia `require_intel_access` (403) aplicada a `/inteligencia/*`, casilla en Configuración, pestañas ocultas en web y Flutter | RF-09.03 |
| 1.2 | Intel: aceptar la API key de servicio en `/alerts`; paginación y filtros (prioridad, tipo, competidor, fecha); quitar el tope de 50; exponer `competidor` (derivado de `data.empresa`) | RF-09.04 |
| 1.3 | Intel: `GET /sag/productos?q=` y `/sag/productos/{registro}` sobre `sag_productos` (búsqueda por nombre, principio activo, titular, registro; índice en Mongo) | RF-09.06/07 |
| 1.4 | Ventas: tabla `intel_lecturas` (alertas leídas por usuario) y contador de no leídas | RF-09.05 |
| 1.5 | Ventas: ficha de producto (SAG + alertas relacionadas; precios y equivalente Encipharm quedan vacíos hasta la Fase 4/D5), con origen y fecha por dato | RF-09.06/11 |
| 1.6 | Proxy robusto: timeouts, caché corta, y **un 401 de Intel no debe llegar como 401 al cliente** (la web cierra sesión); Intel caído → 503 con mensaje | RF-09.10 |
| 1.7 | Flutter: configuración por ambiente y guardia de release contra `localhost`; pestaña Inteligencia (feed con filtros, scroll infinito, tirar para refrescar, detalle, buscador y ficha); caché local de 100 alertas y fichas de 7 días con aviso "datos del dd/mm" | RF-09.01/02/04/08 |
| 1.8 | Pruebas de contrato Ventas↔Intel y las 7 pruebas de aceptación del ERS §3.1 | |

Nota: RF-09.01 ("sin volver a iniciar sesión") se cumple de forma natural: el móvil solo tiene sesión de Ventas.

### Fase 2 — RQ-08: Chat de competencia (ALTA, P0) · tamaño L · depende de la Fase 1

| # | Tarea | RF |
|---|---|---|
| 2.1 | Decidir modelo y proveedor de búsqueda web (D2, D3) con una prueba corta de *function calling* | RF-08.03/11 |
| 2.2 | Servicio de chat en Ventas con herramientas acotadas: `buscar_alertas`, `buscar_producto_sag`, `noticias_competidor`, `precios_competencia` (vacía hasta RQ-04) + búsqueda web. Prompt propio: **sí habla de precios**, solo mercado veterinario, ignora instrucciones dentro de páginas web, responde en español. No tocar las reglas del Consultor Veterinario de Intel | RF-08.02/09 |
| 2.3 | Streaming SSE (`POST /inteligencia/chat/stream`) y paso directo en Ventas | RF-08.05 |
| 2.4 | Tablas de conversaciones y feedback 👍/👎; **tope diario por usuario en Ventas** (hoy toda la CRM comparte las 50 consultas de Intel); registro de uso y costo | RF-08.06/08/10 |
| 2.5 | Fuentes visibles y distinguibles (Intel vs web) | RF-08.04 |
| 2.6 | Flutter: pestaña "Competencia IA" con acceso restringido, preguntas de ejemplo, historial y modo sin conexión | RF-08.01/07/13 |
| 2.7 | Las 6 pruebas del ERS (incluida la de inyección de instrucciones) | |

Riesgo: Intel tiene pocos datos de precio; el chat lo dice y combina con la web.

### Fase 3 — P1: RQ-05, RQ-06, RQ-07 (ALTA) · tamaño L · puede ir en paralelo con la Fase 2

**RQ-05 Usuarios con invitación**
- Estados `invitado/activo/desactivado`; tabla de tokens de invitación con caducidad de 72 h; `POST /users` sin contraseña → email (D4); `POST /auth/set-password`, `forgot-password`, `reenviar-invitacion`.
- Política de contraseña ≥ 10 con letras y números (hoy 8).
- Cerrar el auto-registro público (RF-05.07).
- Ya cumplido: desactivar bloquea al instante (el backend consulta la base en cada request). **No aplican** Google SSO ni el script de duplicados.

**RQ-06 Crear clientes**
- Añadir RUT (migración, validador con dígito verificador, único con mensaje de quién lo tiene) y alinear campos obligatorios web/backend (D8).
- Errores 422 por campo (hoy el contrato `{error,codigo,detalles}` no los lleva al formulario).
- Que supervisor también pueda asignar vendedor (hoy solo admin). Alta de clientes en Flutter (Importante).

**RQ-07 Archivos**
- Documentos RAG: estados Subido → Procesando → Listo/Error con indexación en segundo plano (hoy es síncrona), lista que se actualiza sola, **borrado** (no existe en Ventas), detección de duplicados, límite 25 MB.
- Adjuntos de propuesta: tabla `propuesta_archivos`, endpoints de subida/listado/descarga con enlace firmado (SAS de Azure, no GCS), permisos dueño/supervisor/admin, barra de progreso.

### Fase 4 — P2: RQ-04 → RQ-03 → RQ-01 → RQ-02 (MEDIA) · tamaño XL

| # | Tarea |
|---|---|
| 4.1 | **RQ-04 Competencia:** tablas de producto competidor, **historial de precios** (nunca se pisan), aprobación, equivalencias con el catálogo Encipharm (D5), precio por unidad (ml/g/dosis), endpoint de comparativa, filtros con paginación en base de datos (hoy no hay `ORDER BY` ni offset), resumen por categoría/competidor. Sustituye el stub de `services/competencia.py` |
| 4.2 | **RQ-03 Inteligencia de Mercado (web):** corregir el contrato roto de `AnalisisCompetencia` (espera `{companies, compositions}`, el backend devuelve `{positioning_matrix, share}`), usar datos reales de Fases 1 y 4.1, quitar datos de ejemplo y heurísticas inventadas (`commercialAnalytics.js`, "Prom. industria 35%"), estados de carga/vacío/error y fecha de actualización |
| 4.3 | **RQ-01 Notificaciones:** tabla y endpoints, campana real en `AppShell.jsx`, refresco por consulta periódica (no hay listener tipo Firestore). Ventas **no tiene planificador**: hace falta uno para detectar alertas críticas nuevas de Intel (o un webhook desde Intel). Retención 90 días |
| 4.4 | **RQ-02 Calendario:** tabla `eventos`, endpoints, vista mes/semana/día con arrastrar, vista de supervisor, "realizada" crea la interacción, avisos 24 h/1 h vía RQ-01 |
| 4.5 | Flutter: lista "Mis próximas visitas" (si da el tiempo) |
| 4.6 | **Scrapers Agrovet/Zoetis (captura de WhatsApp):** Playwright añade ~400 MB+ de Chromium; **no cabe** en el proceso del backend de Render free. Solo viable con un servicio aparte o un plan mayor (D6). Primero mejorar datos de precios por reportes de vendedores (RQ-04) |

### Fase 5 — Transversal y cierre (MEDIA-ALTA, continua) · tamaño M

| # | Tarea | RNF |
|---|---|---|
| 5.1 | Auditoría real en SQL (el `audit.py` actual es código muerto de Firestore): quién, qué, cuándo (ISO 8601 con ms), IP y agente | RNF-03 |
| 5.2 | Revisar que todo endpoint exija login salvo `/health`; cerrar `/docs` y `/readiness` en producción; `APP_ENV` por defecto seguro; rotar credenciales; decidir sobre `google-services.json` | RNF-01/02 |
| 5.3 | Cobertura ≥ 70 % del código nuevo, CI con lint, Postgres y chequeo de migraciones | RNF-08 |
| 5.4 | Logs estructurados y alertas (hoy hay `print` y sin métricas) | RNF-09 |
| 5.5 | Textos nuevos en el diccionario i18n; alias `/api/v1` (D7); OpenAPI al día | RNF-07/11 |
| 5.6 | Builds de release Android/iOS firmados contra producción | RNF-06 |
| 5.7 | Actualizar README, `setup.md`, `ARCHITECTURE.md` y `PENDING_FEATURES.md` | |

---

## 4. Dependencias

```
Fase 0 ──► Fase 1 (RQ-09) ──► Fase 2 (RQ-08) ──► Fase 4 (RQ-04 → 03 → 01 → 02)
   │            │                    ▲
   │            └── (campo permiso) ─┤
   └──────────► Fase 3 (RQ-05/06/07, paralela a la 2)
Fase 5: transversal, se cierra al final
```

## 5. Matriz RQ → fase

| RQ | Tema | Prioridad ERS | Fase |
|---|---|---|---|
| RQ-09 | Flutter ↔ Intel | P0 | 0 (base) + 1 |
| RQ-08 | Chat de competencia | P0 | 2 |
| RQ-05 | Usuarios con invitación | P1 | 1 (permiso) + 3 |
| RQ-06 | Crear clientes | P1 | 0 (menú) + 3 |
| RQ-07 | Subida de archivos | P1 | 0 (bugs) + 3 |
| RQ-04 | Competencia backend | P2 | 4 |
| RQ-03 | Inteligencia de Mercado web | P2 | 4 |
| RQ-01 | Notificaciones | P2 | 4 |
| RQ-02 | Calendario | P2 | 4 |

## 6. Riesgos principales

- **Stack distinto al del ERS:** si el PO esperaba Firebase/GCP, se corrige en D1 antes de empezar.
- **Datos de precios escasos:** el chat y las comparativas dependen de reportes de vendedores (RQ-04).
- **Render free:** la latencia de arranque en frío (30–60 s) contradice los p95 del ERS; también limita agentes y planificadores en proceso.
- **Costo del modelo y de la búsqueda web:** tope diario por usuario y registro de costo desde el primer día.
- **Cuota compartida de Intel (50/día):** se elimina moviendo el límite a Ventas (Fase 2).
- **Migraciones sobre datos reales (Supabase):** probar cada migración en una copia antes de aplicarla.
