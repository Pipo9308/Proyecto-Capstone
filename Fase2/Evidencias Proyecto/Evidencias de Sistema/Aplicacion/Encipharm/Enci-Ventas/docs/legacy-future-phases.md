# Fases Futuras y Features Descartadas

Este documento rescata la información sobre características que fueron evaluadas durante las etapas tempranas y MVP del proyecto, pero que fueron descartadas, excluidas del alcance o priorizadas para fases futuras. Toda esta información proviene de los documentos de cierre de sprints, QA y entregas al cliente.

## 1. Riesgos y Features Pendientes de Definición

- **Asistente RAG (Enci Chat)**: 
  - Actualmente requiere el aprovisionamiento de un corpus documental real y validado por el negocio. 
  - Requiere asegurar de forma productiva y segura la API key de DeepSeek.
  - Originalmente se utilizó Chroma DB como motor de persistencia, pero actualmente el código ha migrado para usar PostgreSQL como base de datos vectorial (pgvector) como solución productiva definitiva.

> **Actualización:** Inteligencia de Mercado, Análisis de Competencia, Notificaciones y Calendario ya son operativos (Fases 1–4 del plan de integración, ver `plan-integracion-ers.md`). Lo que sigue describe el estado histórico previo.

- **Inteligencia de Mercado / Análisis de Competencia**:
  - El frontend tiene interfaces preparadas (estáticas) y el backend tiene soporte básico, pero el flujo está **no operativo**.
  - Razón: Aún no existe definición de negocio, fuentes de datos, método legal de captura ni responsables de carga de datos competitivos.

## 2. Features Descartadas o No Operativas

- **Notificaciones**: 
  - La UI puede mostrar marcadores visuales, pero el modal muestra "No operativo".
  - Razón: No existe definición de flujo, origen de datos (push, in-app, correos) ni reglas de marcado de lectura.

- **Calendario Operativo**: 
  - Marcado como "No operativo".
  - Razón: No existe definición de integraciones (ej. Google Calendar) ni modelo de persistencia de agenda interna.

- **Mapa de Alertas y Actividad**: 
  - Muestra "No operativo".
  - Razón: No existe definición de georreferenciación avanzada ni proveedor de mapas productivo.

## 3. Exclusiones de Alcance Históricas

Las siguientes características y plataformas quedan fuera del código real web actual y fueron documentadas como exclusiones formales:

- Integración con ERP SAP.
- Google Calendar operativo o agendas integradas.
- Integraciones nativas con WhatsApp productivo.
- Funciones avanzadas de OCR (Reconocimiento Óptico de Caracteres).
- Firmas digitales integradas en propuestas o contratos.
- Reportes BI (Business Intelligence) extendidos más allá de los dashboards estándar.
- Funcionalidad Offline Total en el CRM web.
- La publicación de la aplicación móvil (Flutter) en Play Store o App Store (aunque el código fuente de `vendedor_app_flutter` está en el repositorio, la gestión en tiendas es externa).
- Fine-tuning de modelos LLM o evaluación masiva con SLA del proveedor de IA; actualmente el RAG se enfoca en inyección de contexto dinámica (Zero-shot + Context).

## 4. Hardening y Deuda Técnica Pendiente

- Migrar el rate limit (actualmente in-memory por proceso) a almacenamiento compartido (como Redis) si el backend se escala a múltiples instancias.
- Convertir listados de Firestore/PostgreSQL a queries compuestas estrictas para reducción de latencia en consultas muy voluminosas.
- Pruebas E2E (End-to-End) con herramientas tipo Playwright automatizadas dentro del pipeline CI/CD en un ambiente staging idéntico a producción.
