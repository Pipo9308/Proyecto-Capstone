# Revisión del código en duro (hardcode)

Fecha: 2026-10-26. Motivo: se comentó que el proyecto tiene mucho código en duro. Esta es una **lectura**, no se cambió código.
Método: barrido por búsqueda de patrones (URLs, nombres de empresas, constantes, números fijos, colecciones) sobre
`Enci-Intel` y `Enci-Ventas`. No es una auditoría línea por línea y puede dejar casos fuera.

## Qué está bien
- Claves y credenciales (JWT, API keys, Firebase, `DEEPSEEK_*`) van por variables de entorno, no en el código.
- El modelo de IA ya es configurable desde la pantalla "Modelo de IA" (ver README, 2026-10-26).
- Casi todas las URLs de servicio (`REDIS_URL`, `ENCI_INTEL_API_URL`, `VITE_API_BASE_URL`) ya se leen del entorno.

## Hallazgos por prioridad

### 1. Competidores, fuentes y sitios (el más importante)
- **SAG**: la lista de nombres de competidores está escrita en `Enci-Intel/Backend/agents/agent-sag/scraper.py` (alrededor de las
  líneas 42-46: Drag Pharma, Zoetis, Agrovet…). El scraper intenta leer la colección `competitors`, pero está vacía, así que
  siempre cae a esa lista.
- **Competidores**: la URL de Drag Pharma (`DRAG_PHARMA_NOTICIAS_URL`), el filtro `dragpharma.cl` y la lista `FUENTES_PRENSA`
  (Zoetis y Agrovet, con su consulta y su palabra clave) están en `agents/agent-competidores/scraper.py`. El texto de
  `agents/agent-competidores/main.py` también nombra a las tres empresas.
- **Efecto**: agregar o quitar un competidor exige editar código y redesplegar, en dos agentes distintos.

### 2. Datos de demostración que parecen reales
- Colecciones sembradas a mano con `Enci-Intel/Backend/scripts/seed_demo_data.py`: `products` (2 productos de ejemplo),
  `market_share` (mercado de 4,2 millones de dólares, Q1-2026) y `positioning_matrix`. El dashboard de Intel las muestra como si
  fueran datos del negocio.
- `products` además es el catálogo con el que el agente SAG busca solapamiento: con 2 productos de demostración casi nunca
  detecta nada.

### 3. Reglas de negocio no configurables
| Regla | Dónde |
|---|---|
| Urgencia por categoría del SAG (80/65/55, cancelaciones 90/75/65) | `agents/agent-sag/detector.py` (`_resolve_urgency`, `CATEGORIAS_ESTRATEGICAS`) |
| Vigencia de alertas por prioridad (24 h, 72 h, 7 días, 30 días) | `_EXPIRY_DELTA` en ambos `detector.py` (duplicado) |
| Umbrales de prioridad (80/60/40) | `_urgency_to_priority` en ambos agentes y `_resolve_priority` en `app/api/alerts.py` (triplicado) |
| Límite diario de consultas al chat (50) | `app/api/rate_limiter.py` (`DAILY_LIMIT`) |
| Duración del token de sesión (7 días) | `app/api/auth.py` |
| Tope de registros SAG analizados por corrida (40), tamaños de lote | `agents/agent-sag/enriquecedor_sag.py`, `agents/agent-competidores/enriquecedor.py` |
| Bono de urgencia por solapamiento (+15) | `agents/agent-sag/detector.py` |
| Caché de 60 s y 120 s | `app/api/*` y `Enci-Ventas/.../llm_runtime.py` |

### 4. Prompts y filtros dentro del código
- Prompts largos en `Enci-Intel/Backend/app/rag/engine.py` (`_RULES`, `SYSTEM_PROMPT`, `GENERAL_PROMPT`), en
  `Enci-Ventas/Backend/app/services/llm_service.py` (`build_system_prompt`, 13 reglas) y en `competencia_chat.py`.
- Los patrones de `solo_animales.py` están **duplicados** en `Enci-Intel/Backend/app/rag/` y `Enci-Ventas/Backend/app/services/`.
  Si cambia uno y no el otro, los chats se comportan distinto.

### 5. Textos y catálogos en el frontend
- Etiquetas en español e inglés repetidas página por página (por ejemplo, 13 bloques solo en `Enci-Intel/Frontend/src/pages/Alertas.tsx`).
- Catálogos en el código: categorías de documentos y colores (`AdminDocumentos.tsx`), tipos, iconos y niveles de alerta
  (`Alertas.tsx`), proveedores y modelos sugeridos (`AdminModeloIA.tsx`), roles y rangos (`Enci-Ventas/frontend/src/auth/roles.js`),
  etapas del embudo comercial.
- Existe `Enci-Intel/Frontend/src/i18n/translation.ts`, pero muchas páginas no lo usan.

### 6. URLs y entorno
- `localhost` fijos en la lista de CORS (`Enci-Intel/Backend/app/main.py`, `Enci-Ventas/Backend/app/core/config.py`) y valor por
  defecto de `API_BASE` en `ConsultorVet.tsx`. Son valores por defecto para desarrollo; hay que verificar que producción
  siempre defina las variables.
- Hosts externos en la política de seguridad de contenido (`Enci-Ventas/Backend/app/main.py`: `unpkg.com`, `gstatic.com`) y la URL de
  Tavily (`web_search.py`). Aceptables como constantes con nombre.
- Nombres de colecciones de Firestore escritos como literales en muchos archivos (`agents`, `alerts`, `users`, `products`…).

## Enci-Ventas (revisión aparte)
En general es más limpio que Intel: casi todo está en `Backend/app/core/config.py` (`Settings`) y se sobreescribe por entorno, y la
app Flutter recibe la URL del servidor con `--dart-define=API_URL` y rechaza compilar para producción apuntando a localhost.

### V1. La "Meta del Mes" no es una meta real
- En `frontend/src/utils/forecastExport.js` (`calculateForecastTarget`) la meta se calcula como el mayor entre el pipeline abierto y lo
  ya cerrado (propuestas aceptadas). No existe una meta por vendedor guardada en ninguna parte.
- Los gráficos de cumplimiento y brechas del dashboard y de la exportación del forecast se miden contra ese número derivado.
- Es la lógica de negocio más delicada de las que están "escondidas" en el código: da la impresión de que hay una meta cuando no la hay.

### V2. Reglas de negocio fijas en el código
- **Etapas del embudo**: `STAGES` y `STAGE_LABELS` en `frontend/src/utils/commercialAnalytics.js` (nuevo, contactado, cotización,
  negociación, ganado). La probabilidad sí viene de cada oportunidad.
- **Zonas**: las cuatro (norte, centro, sur, oriente) están en `Backend/app/models/user.py` (`ZONE_ALIASES`); agregar una zona exige
  cambiar código.
- **Roles y rangos duplicados**: `ROLE_ALIASES` y `RANK_ALIASES` en el backend y `ROLE_RANKS` / `ROLE_LABELS` en
  `frontend/src/auth/roles.js`. Si cambian en un lado, el otro queda desalineado.
- **Moneda**: CLP fijo en los formularios de precios (`components/competencia/`).
- **Parámetros sueltos**: duración máxima de un evento (12 h, `models/evento.py` y `MAX_HOURS` en el formulario), largo mínimo de
  contraseña (10, `core/password_policy.py`), umbral de ventana de no leídos (`api/inteligencia.py`). Los de `config.py` ya son
  configurables por entorno.

### V3. Datos de ejemplo
- `Backend/scripts/seed_demo_fase4.py` y `seed_max_wellq_demo.py` siembran datos de demostración: no deben correr contra el Firestore
  real.

## Plan propuesto (cada paso se puede entregar solo)

**Paso 1 — Competidores editables.** Colección `competitors` en Firestore (nombre, alias, nombres legales del SAG, sitio de
noticias, consulta de prensa, palabra clave, activo). Los dos agentes la leen y, si está vacía, siembran los valores actuales para no
romper nada. Pantalla de administración en Intel (solo admin) para agregar, editar y desactivar.
- Hecho cuando: agregar un competidor desde la pantalla hace que el siguiente run de ambos agentes lo incluya, sin tocar código.

**Paso 2 — Sacar los datos de demostración.** Cargar el catálogo real de Encipharm en `products` (con principio activo, especie y
categoría) mediante una importación desde Excel o CSV en la pantalla de administración. Marcar o retirar `market_share` y
`positioning_matrix` hasta que haya datos reales; el dashboard debe decir "sin datos" en vez de mostrar cifras de ejemplo.

**Paso 3 — Parámetros de negocio en configuración.** Un documento `app_settings/negocio` con urgencias por categoría,
vigencias, límite diario y vigencia del token; los valores actuales quedan como respaldo. Reutilizar el patrón de `llm_settings.py`
y una sola función de umbrales en vez de tres copias.

**Paso 4 — Unificar prompts y filtros.** Un único módulo compartido para `solo_animales` (hoy duplicado) y los prompts agrupados
en archivos propios, con la posibilidad de editarlos desde la pantalla más adelante.

**Paso 5 — Frontend ordenado.** Mover los textos es/en a `translation.ts` y los catálogos (tipos de alerta, categorías,
proveedores) a un archivo de constantes por módulo. Prioridad: `Alertas.tsx`, `Dashboard.tsx`, `AdminDocumentos.tsx`.

**Paso 6 — Entorno.** Revisar que producción defina todas las variables y que los valores por defecto de desarrollo no puedan
quedar activos; centralizar los nombres de colecciones en un módulo.

**Paso 7 — Ventas: metas reales y catálogos.** Colección de metas (vendedor, mes, monto) que el supervisor edita; el dashboard y
el forecast miden contra ella y, si no hay meta cargada, muestran "sin meta" en vez de un valor derivado. Zonas y etapas del embudo
como catálogos configurables, con una sola definición de roles y rangos expuesta por el backend y consumida por la web.
- Hecho cuando: el supervisor fija una meta y el dashboard refleja el cumplimiento real contra ella.

## Riesgos
- Mover reglas a configuración las vuelve editables por un admin: validar rangos (0-100, días positivos) y dejar el valor actual
  como respaldo si el documento falta o está mal.
- El paso 1 cambia la fuente de los nombres del SAG: el nombre debe coincidir exactamente con el registrante del listado oficial
  (por ejemplo "ZOETIS DE CHILE S.A."), así que la pantalla debe pedir los nombres legales, no solo el alias.
- Sin pruebas de los scrapers (Drag Pharma, SAG, prensa): conviene agregar pruebas con HTML de ejemplo antes de refactorizar.
