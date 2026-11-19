# Sesión de trabajo: Fases 4–5, migración total a Firestore y pruebas E2E

Resumen de lo hecho en esta sesión (septiembre–octubre 2026). Complementa `Enci-Ventas/docs/plan-integracion-ers.md` y
`MIGRACION_FIREBASE.md`. Los pendientes están al final.

## 1. Resultado en una frase

Enci-Ventas y Enci-Intel guardan **todo** en una única base: Cloud Firestore, proyecto `encipharm-12321`
(`southamerica-west1`). PostgreSQL (Supabase), MongoDB (Atlas) y Qdrant dejaron de usarse en producción.

## 2. Qué se hizo

### Plan de integración ERS (Fases 4 y 5, Enci-Ventas)
- Fase 4: comparador de competencia con precio por unidad, reporte de precios por vendedores con aprobación del
  supervisor, catálogo de productos Encipharm, chat de competencia con herramientas (alertas, SAG, noticias, precios, web).
- Fase 5: calendario (límite de 12 h, «realizada» queda en el historial, arrastrar a otro día), notificaciones sin
  planificador (el mantenimiento corre al consultar, como máximo una vez por minuto) y avisos de propuestas.
- Datos de demostración: `Enci-Ventas/Backend/scripts/seed_demo_fase4.py`; usuarios en `seed_admin.py`.

### Enci-Intel → Firestore
- `app/firestore_db.py`: capa con API tipo Mongo (una condición en el servidor + filtro en Python, fechas naive UTC).
  Soporta `FIREBASE_CREDENTIALS_JSON` (JSON en una línea) y limpia el id del proyecto (`clean_project_id`).
- RAG: vectores de 2048 dimensiones en `intel_docs` (`app/rag/store.py`, `find_nearest` COSINE).
- Agentes (`agents/*/db_session.py`) usan la misma capa en modo síncrono.
- Scripts: `migrate_mongo_to_firestore.py`, `migrate_qdrant_to_firestore.py`, `create_vector_index.py`.

### Enci-Ventas → Firestore
- `app/core/odm.py`: ODM propio con la forma de SQLAlchemy (`Field/Column/Document/Session/Query`). Unicidad con
  documentos guardia atómicos (`ventas__unique`), todas las igualdades se resuelven en el servidor (sin índices
  compuestos), `Session.nearest()` para vectores (384 dims en `ventas_rag_chunks`), prefijo `ventas_`.
- Se quitó SQLAlchemy/Alembic del arranque; todos los modelos de `app/models_sql/*` se convirtieron.
- Scripts: `migrate_postgres_to_firestore.py` (con `--replace`), `create_vector_index.py`.
- Contratos REST `/api/v1/...` sin cambios (el frontend y Flutter no se tocaron para esto).

### Producción
- Render: ambos backends con `FIREBASE_PROJECT_ID` + `FIREBASE_CREDENTIALS_JSON`; Start Command sin Alembic.
- Cutover de Ventas verificado por el usuario (vio sus clientes en producción). Índices vectoriales creados y listos.

### Pruebas
| Suite | Cantidad | Cómo corre |
|---|---|---|
| Ventas backend | 507 | contra el emulador de Firestore (`FIRESTORE_EMULATOR_HOST` obligatorio) |
| Intel backend | 157 | + pruebas de emulador/real con credenciales |
| Web | 140 | Vitest |
| Flutter | 67 | `flutter test` |
| E2E Playwright | 35 | `Enci-Ventas/e2e/` (ver su README), Edge real contra el stack local |

El emulador no soporta vectores: las pruebas de vectores solo corren con credenciales reales.

## 3. Incidentes y cómo se resolvieron
| Incidente | Causa | Arreglo |
|---|---|---|
| Login de Ventas con 500 en producción | migraciones de Alembic sin aplicar | se aplicaron; luego se migró a Firestore |
| Render no arranca (Secret File / JSON vacío) | archivo secreto no encontrado | `FIREBASE_CREDENTIALS_JSON` en una línea |
| `CONSUMER_INVALID` 403 | id del proyecto con punto final / mal escrito | `clean_project_id` + valor corregido |
| Cliente Firestore con `dns:///` | `FIRESTORE_EMULATOR_HOST` vacío | se elimina la variable si está vacía |
| Se borraron todos los índices de Firestore | un bucle de limpieza mío | se recrearon |
| Se borró `Backend/api/index.py` | error mío | restaurado con `git checkout` |
| E2E inestables | selectores, orden entre pruebas, autoreload al sembrar | pruebas independientes + `esperarApi()` |

## 4. Hallazgos
- 20 puntos del análisis inicial (memoria `encipharm-verified-bugs-2026-10-12`).
- Revisión de agentes: `docs/revision-agentes-sag-competidores.md`.
- Plan del RAG: `docs/plan-rag-gemini-solo-animales.md`.

## 5. Pendientes
**Seguridad (urgente).** Se pegaron en el chat y deben **rotarse**: clave de cuenta de servicio de Firebase
(`c51e8bd7…`), contraseña de Supabase, usuario/clave de Atlas, Upstash y la API key de Qdrant. El JSON de la cuenta de
servicio está en la raíz del repo (ignorado por `.gitignore`, pero conviene borrarlo del disco tras rotarlo).

**Limpieza.** Apagar Supabase, Atlas y Qdrant; quitar `DATABASE_URL`/`MONGODB_URL` de Render; borrar índices
`vec_prueba*`; archivos sueltos en la raíz (`message.txt`, `Log errors.txt`, `logs*.txt`).

**Costos.** La campana de notificaciones consulta cada 30 s: vigilar lecturas de Firestore.

**Producto.** Adjuntos siguen en Azure Blob (decidir si pasan a Firebase Storage; hoy hay 0 archivos). RAG de Intel sin
documentos indexados. Chat de competencia sin API key de modelo. Flutter: próximas visitas, reportar precios, crear
cliente/adjuntos y build firmado.

**Git.** Los commits E2E (`67fc8b0`, `e94a1c2`) pueden no estar en `main` remoto: revisar con `git status`.
