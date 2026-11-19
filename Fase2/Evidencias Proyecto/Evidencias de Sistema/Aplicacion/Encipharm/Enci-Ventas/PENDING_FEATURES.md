# Estado de funcionalidades y pendientes

Actualizado al cerrar las Fases 0–5 del plan de integración con el ERS (`docs/plan-integracion-ers.md`).
Ese documento es la fuente de verdad: aquí solo va el resumen.

## Operativo

| Módulo | Dónde | Notas |
|---|---|---|
| Inteligencia de Mercado (alertas, chat de competencia, comparación de precios y de composición) | Web `/inteligencia`, `/competencia`; Flutter (pestaña Intel) | Datos reales de Enci-Intel y de los precios que reportan los vendedores. Requiere el permiso «Acceso a Inteligencia» |
| Competencia (RQ-04) | API `/competencia/*` | Historial de precios con aprobación, catálogo Encipharm y equivalencias |
| Notificaciones (RQ-01) | Campana de la web | Alertas de Intel, propuestas, clientes asignados, documentos RAG y visitas próximas. Se guardan 90 días |
| Calendario (RQ-02) | Web `/calendario` | Mes/semana/día, arrastrar entre días, «realizada» deja la visita en el historial del cliente |
| Usuarios con invitación (RQ-05) | Web y Flutter | Enlace de un solo uso copiado por el admin; sin envío de correo |
| Clientes con RUT (RQ-06) | Web | RUT obligatorio y único |
| Documentos RAG y PDF de propuestas (RQ-07) | Web | Estados, borrado, duplicados y enlaces de descarga firmados |
| Auditoría (RNF-03) | API `/auditoria` (solo admin) | Quién, qué, cuándo, IP y agente; sin cuerpos ni contraseñas |

## Pendiente

- **Probar el chat de competencia con un modelo real**: falta `DEEPSEEK_API_KEY` (y `TAVILY_API_KEY` para la búsqueda web). Hay que elegir un modelo con *function calling* fiable y medir tiempos.
- **Envío de correos** (invitación, restablecer contraseña): hoy el admin comparte el enlace.
- **Flutter**: «Mis próximas visitas», alta de cliente, adjuntos y reporte de precios desde la app.
- **Carga masiva** de listas de precios y del catálogo Encipharm (CSV/Excel).
- **Catálogo real de Encipharm**: lo entrega el PO; el que hay en desarrollo es de prueba.
- **Scrapers de Agrovet/Zoetis**: no caben en el hosting actual (Render free, 512 MB).
- **Silenciar tipos de aviso** (RF-01.06) y detectar alertas de Intel sin que nadie tenga la web abierta (hoy no hay planificador).
- **Cerrar las sesiones abiertas** al cambiar la contraseña (el token dura 7 días).
- **Builds de release firmados** de Android e iOS (el de Android nunca se completó en la máquina de desarrollo).
- **Suite de tests sobre Postgres**: hoy corre sobre SQLite; en el CI Postgres se usa para verificar las migraciones. Los tests antiguos usan UIDs falsos que Postgres rechaza por las claves foráneas.
- **Traducciones**: solo la barra lateral y Configuración están en el diccionario i18n; las pantallas nuevas están solo en español.
- **Métricas y alertas**: los logs son estructurados (JSON) y los errores 5xx salen con nivel ERROR, pero no hay un sistema de métricas ni reglas de alerta configuradas en el hosting.
