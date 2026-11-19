# Evidencias de sistema — Base de datos

Proyecto: **Inteligencia de Mercado (Enci-Intel + Enci-Ventas)** · APT122 · Grupo 1

La solución usa **Cloud Firestore** (base NoSQL de documentos de Google Cloud), compartida por Enci-Ventas y Enci-Intel,
con **índices vectoriales nativos** para el asistente RAG.

## Contenido

| Archivo / carpeta | Qué es |
|---|---|
| `Diccionario_de_datos.docx` | Descripción de cada colección y sus campos, la evolución del modelo y los diagramas |
| `Modelo_de_datos.pdf` | Diagramas del modelo de datos (página 1: Enci-Ventas · página 2: Enci-Intel) |
| `diagramas/` | Los mismos diagramas en PNG y su fuente Graphviz (`.dot`) |
| `modelos/enci-ventas/` | Definición de las 21 colecciones de Ventas (`*.py`) y la capa de acceso a Firestore (`odm.py`) |
| `modelos/enci-intel/` | Capa de acceso a Firestore de Intel (`firestore_db.py`) |
| `scripts/migraciones/` | Scripts de migración de datos hacia Firestore (ver abajo) |
| `scripts/seeds/` | Scripts de carga de datos iniciales y de demostración |
| `scripts/indices/` | Creación de los índices vectoriales de Firestore (384 dimensiones en Ventas, 2048 en Intel) |

Estos archivos son copias tomadas del código fuente (`../Aplicacion/Encipharm/`), reunidas aquí para revisarlas
sin buscar dentro del proyecto.

## Evolución del modelo de datos

El modelo cambió dos veces por solicitud de la empresa:

1. **Fase 1:** arquitectura original de Enci-Intel en Google Cloud Platform (Firestore, Cloud Run, Cloud Scheduler).
2. **Fase 2 (agosto–septiembre 2026):** Enci-Intel y Enci-Ventas se unificaron en un monorepo y Enci-Intel se migró de
   Firestore a MongoDB Atlas (completado el 14 de agosto). Enci-Ventas quedó en PostgreSQL (Supabase), con Qdrant para la
   búsqueda vectorial y Redis (Upstash) para caché. Con esa base se cumplió el MVP del Hito 1 (29 de septiembre).
3. **15–18 de octubre de 2026:** tras una reunión de alineación con el stakeholder técnico de la empresa (15 de octubre),
   se decidió unificar toda la capa de datos en Cloud Firestore. La migración se ejecutó en 72 horas y terminó el
   18 de octubre:

| Script | Migra |
|---|---|
| `migrate_postgres_to_firestore.py` | Enci-Ventas: PostgreSQL → Firestore |
| `migrate_mongo_to_firestore.py` | Enci-Intel: MongoDB → Firestore |
| `migrate_qdrant_to_firestore.py` | Vectores del RAG: Qdrant → Firestore Vector Search |

Los scripts son idempotentes (repetirlos no duplica datos) y por defecto funcionan en modo de prueba; con `--apply` escriben.

## Cómo crear la base desde cero

Firestore no usa un script de creación de tablas: las colecciones se crean al escribir el primer documento.

```bash
# desde Encipharm/Enci-Ventas/Backend (o Enci-Intel/Backend), con FIREBASE_PROJECT_ID y FIREBASE_CREDENTIALS_PATH definidos
uv run python scripts/create_vector_index.py   # índice vectorial del RAG
uv run python scripts/seed_admin.py            # usuario administrador (clave en ADMIN_PASSWORD)
uv run python scripts/seed_demo_sintetico.py   # datos de demostración de Ventas (--borrar los quita)
```

Los datos de los scripts de demostración son ficticios.
