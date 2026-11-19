# Revisión de los agentes SAG y Competidores (Enci-Intel)

Revisión por lectura de código (2026-10-18). **No se modificó código ni se ejecutó contra producción.** Archivos:
`Enci-Intel/Backend/agents/agent-sag/{main,scraper,detector,db_session}.py`,
`agents/agent-competidores/{main,scraper,detector,db_session}.py`, `app/scheduler.py`, `app/api/agents.py`.

## Qué hace cada uno
- **SAG**: descarga el listado oficial de medicamentos veterinarios del SAG (HTML disfrazado de .xls), lo filtra por
  nombres de competidores, lo compara con `sag_productos` y crea alertas `sag_newsku_*` (nuevo registro) y
  `sag_cancel_*` (registro que desaparece). La urgencia depende de la categoría (antimicrobianos e inmunológicos mayor).
- **Competidores**: scrapea `dragpharma.cl/noticias/` (hasta 6 páginas), guarda en `competitor_news` y crea alertas
  `comp_noticia_*`. Solo cubre Drag Pharma.
- Ninguno usa un modelo de lenguaje: **no dependen del cambio a Gemini**. Ya escriben en Firestore con `app/firestore_db.py`.

## Hallazgos (de mayor a menor)

### Altos
1. **Cancelaciones masivas falsas (SAG).** `cancelados = previos − actuales`. Si el SAG responde vacío o cambia el HTML,
   o el filtro por nombre (`isin` exacto en mayúsculas) deja de coincidir, **todos** los productos pasan a
   «cancelado» y se crea una alerta por cada uno. No hay ninguna validación de cordura (p. ej. abortar si
   `len(df)` cae más de X % o es 0).
2. **Los agentes no se programan solos ni se pueden lanzar la primera vez.** En `app/main.py` el scheduler solo hace
   `start_scheduler()`: no carga los cron guardados en `agents`. Además la colección `agents` solo la crea el propio
   agente al correr, y `/run`, `/schedule`, `/enabled` devuelven 404 si el documento no existe. Resultado: en una base
   nueva no se puede ejecutar ni programar ningún agente desde el panel. Y los cron en memoria se pierden en cada
   reinicio.
3. **Render gratis duerme el servicio** a los ~15 min: un APScheduler dentro del backend no dispara nada mientras
   duerme. Para ejecuciones periódicas reales hace falta un disparador externo (Render Cron Job, GitHub Actions o Cloud
   Scheduler llamando a `POST /agents/{id}/run`).
4. **Ejecución como subproceso «dispara y olvida».** `subprocess.Popen(["python", ...])`: sin código de salida, sin
   logs, sin `wait` (zombies), ruta relativa (`agents/...` y `sys.path.insert(0, 'agents/agent-sag')` solo funcionan con
   el directorio de trabajo en `Backend`) y con 512 MB de Render un segundo Python con pandas junto a la API puede morir
   por memoria. Si el proceso muere, el run queda en `running` para siempre (y la API deja de cachear los runs).

### Medios
5. **Primera ejecución = avalancha de alertas.** Con `sag_productos` / `competitor_news` vacíos, todo es «nuevo». Para
   Competidores existe `--populate-only`; para SAG no. Verificar el estado real de `sag_productos` en producción
   (venía de Mongo) antes de la primera corrida.
6. **Scraper SAG frágil.** Asume `tables[0]` encabezados y `tables[1]` datos, decodifica como UTF-8 aunque el comentario
   dice latin-1, y `pd.DataFrame(data, columns=headers)` falla si una fila tiene otra cantidad de columnas. Sin pruebas
   con un HTML de ejemplo.
7. **`db.competitors` no existe en Firestore.** El scraper SAG lee esa colección para los nombres; no está entre las
   colecciones migradas, así que siempre cae a la lista fija de 5 nombres. Decidir: crear la colección (con alias) o
   quitar la lectura.
8. **Cancelaciones con N+1 consultas.** En `generar_alertas`, por cada cancelación se hace `update_one` + `find_one`
   (y `sincronizar_productos` ya había marcado el producto). Con muchas cancelaciones son cientos de lecturas/escrituras
   Firestore secuenciales; usar lectura por lote y un solo `bulk_write`.
9. **Estados inconsistentes.** Al terminar, `main` fija `status: active` aunque el agente esté deshabilitado
   (`idle`) y no actualiza `last_run` al final.
10. **Competidores: cobertura y duración.** Solo Drag Pharma (Zoetis y Agrovet no tienen scraper de noticias); pide el
    artículo completo de cada noticia con pausas de 0,5–1 s (minutos por corrida); la fecha se guarda como texto sin
    parsear; todas las alertas son tipo `LAUNCH` aunque sea una nota cualquiera; lee toda `competitor_news` en cada
    corrida.

### Bajos
11. Usar `sys.executable` en vez de `"python"`.
12. `/agents` se cachea 60 s: tras ejecutar, el panel puede mostrar datos viejos.
13. Pruebas: SAG tiene `test_agent_sag_urgency.py` y `test_agents_firestore.py` (solo detector, con emulador);
    Competidores y los scrapers no tienen pruebas.

## Plan propuesto
1. **Guarda de cordura en SAG** (hallazgo 1) con prueba. Es lo más peligroso: genera alertas falsas visibles al comercial.
2. **Sembrar `agents`** (`agente_sag`, `agente_competidores`, con `schedule` y `enabled`) al iniciar si faltan, y
   cargar los cron guardados en `start_scheduler` (hallazgo 2).
3. **Disparador externo** para producción (hallazgo 3) y pasar de `Popen` a ejecución con captura de salida y marcado
   de runs huérfanos como `failure` al arrancar (hallazgo 4).
4. Corrida controlada: `agent-competidores --populate-only` y SAG con la guarda, revisando `agent_runs`.
5. Resolver `competitors` (7), N+1 (8) y estados (9); pruebas del scraper con HTML de ejemplo (6, 13).
6. Ampliar Competidores a Zoetis/Agrovet si el negocio lo pide (10).

## No verificado
No se ejecutaron los agentes ni se consultó Firestore de producción; los puntos 5 y 7 dependen del contenido real de la
base. El resto sale directamente del código leído.

## Actualización 2026-10-26
Se ejecutaron ambos agentes contra el Firestore real (`encipharm-12321`) y se aplicaron cambios. Estado de los hallazgos:

- **Funcionan, pero no traen novedades**: SAG descarga 404 registros (los mismos que hay guardados: 0 nuevos, 0 cancelados);
  Drag Pharma tiene 35 noticias, todas de 2023-2024. Un panel vacío se debía a que las alertas expiraban a los 7 días
  y a que ningún agente corre solo, no a un fallo del scraping.
- **Alertas vencidas (nuevo)**: la API ya no las filtra y el agente SAG ya no las borra (`limpiar_alertas_vencidas`
  eliminada). Se reconstruyeron las 404 alertas `sag_newsku_*` de la primera corrida (29-09) desde `sag_productos`.
- **Hallazgo 10 (cobertura)**: Competidores ahora cubre Zoetis y Agrovet vía RSS de Google News
  (`scraper.scrape_prensa`, `FUENTES_PRENSA`). Agrovet se filtra por el título `agrovet market`. Menciones de prensa,
  no comunicados; si Google cambia o bloquea el RSS, esas fuentes quedan vacías sin avisar.
- **Frontend de Intel**: `getAlerts` recorre todas las páginas; antes solo veía las 50 más nuevas.
- **Siguen abiertos**: 1 (guarda de cordura en SAG), 2 (programador sin cargar los cron y sin sembrar `agents`),
  3 (Render duerme), 4 (subproceso sin captura de salida), 5-9 y 11-13. Sin pruebas del scraper de prensa
  (verificado con dry-run y corrida real). Las URLs de prensa son enlaces de Google News que redirigen al artículo.
- **Corrección sobre el texto original**: la vigencia de las alertas de competidores es 7 días (urgencia 55, "medium").
