# Evidencias de documentación

Proyecto: **Inteligencia de Mercado (Enci-Intel + Enci-Ventas)** · APT122 · Grupo 1
Integrantes: Felipe Ramos, Benjamín Pumarino, Elías Sánchez

Documentación técnica y de gestión del proyecto. Los documentos técnicos (carpetas 01 a 05) provienen del
repositorio de desarrollo y se convirtieron a Word. Cada documento refleja la etapa del proyecto en que se escribió:
el proyecto cambió dos veces de base de datos por solicitud de la empresa, y esas versiones se conservan como evidencia.

## 01_Arquitectura

| Documento | Contenido |
|---|---|
| `Arquitectura_actual.docx` | **Arquitectura vigente**: componentes, integración Ventas ↔ Intel y despliegue |
| `Arquitectura_Enci-Intel_version_original.docx` | Arquitectura original de Enci-Intel sobre Google Cloud (etapa inicial) |
| `Arquitectura_Enci-Ventas_etapa_PostgreSQL.docx` | Arquitectura de Enci-Ventas en la etapa PostgreSQL (Fase 2, previa a Firestore) |
| `Referencia_API_Enci-Ventas.docx` | Endpoints de la API de Enci-Ventas |

## 02_Requisitos

| Documento | Contenido |
|---|---|
| `Plan_integracion_requisitos_ERS.docx` | Contraste entre la especificación de requisitos (ERS) de la empresa y el sistema real, con brechas y decisiones |

## 03_Instalacion

| Documento | Contenido |
|---|---|
| `Manual_instalacion_Enci-Ventas.docx` | Configuración y puesta en marcha del backend, frontend y app móvil |
| `Guia_incorporacion_equipo.docx` | Guía para levantar el proyecto completo y cargar datos de demostración |

## 04_Calidad_y_revisiones

| Documento | Contenido |
|---|---|
| `Revision_codigo_en_duro.docx` | Revisión de valores fijos en el código y plan de corrección |
| `Revision_agentes_SAG_y_Competidores.docx` | Revisión de los agentes de scraping: 13 hallazgos priorizados |

Las pruebas automatizadas (más de 900, en 5 suites) y la integración continua están en el código:
`Evidencias de sistema/Aplicacion/Encipharm/` (carpetas `tests/`, `e2e/` y `.github/workflows/ci.yml`).

## 05_Gestion_y_cambios

| Documento | Contenido |
|---|---|
| `Sesion_migracion_a_Firestore.docx` | Registro de la migración total a Firestore (15–18 de octubre de 2026) |
| `Plan_RAG_solo_animales_y_Gemini.docx` | Plan del asistente RAG restringido a temas veterinarios y cambio de modelo de IA |
| `DefinicionProyecto_v2_Supabase-MongoDB.docx` | Definición del proyecto actualizada en Fase 2 (cambio de base de datos solicitado por la empresa) |
| `DefinicionProyecto_v3_Firestore.docx` | **Versión final** de la definición del proyecto, con el plan de trabajo y la **Carta Gantt vigente** (actualizada tras la migración a Firestore) |

La versión 1 de la definición es la guía 1.5, en `Fase 1/Evidencias Grupales/`.

## 06_Presentaciones_de_avance

| Documento | Contenido |
|---|---|
| `PPT_Avance_Fase2_2026-09-24.pptx` | Informe de avance presentado a la docente (evidencia E1) |
| `PPT_Avance_Fase2_2026-09-30.pptx` | Avance posterior al Hito 1 (MVP con base de datos operativa) |

## 07_Capturas_de_evidencias

Capturas de los anexos A y B del informe final de Fase 2 (`2.6_GuiaEstudiante_Fase2_InformeFinalProyectoAPT`),
en resolución original. El prefijo de cada archivo es el ID de la evidencia en el informe.

| ID | Capturas | Qué muestra | Evidencia |
|---|---|---|---|
| A-1 | `A-1_Docker_imagenes_del_proyecto.png` | Ambiente local en Docker con las imágenes del proyecto | E1 |
| A-2 | `A-2_Deploy_Render_Enci-Intel_API.png`, `A-2_Deploy_Vercel_Enci-Ventas.png`, `A-2_Deploy_Vercel_Enci-Intel.png` | Despliegue público en Render y Vercel | E3 |
| A-3 | `A-3_Consultor_IA_Enci-Intel.png`, `A-3_Asistente_RAG_Enci-Ventas.png` | Asistentes RAG respondiendo consultas reales | E3 |
| A-4 | `A-4_Supabase_tablas_Enci-Ventas.png`, `A-4_MongoDB_Atlas_Enci-Intel.png` | MVP con bases de datos operativas (404 registros SAG reales en Atlas) | E2 |
| A-5 | `A-5_Lint_y_build_frontend_Enci-Ventas.png`, `A-5_Build_frontend_Enci-Intel.png` | Lint y build de producción de ambos frontends sin errores | E4 |
| A-6 | `A-6_Salida_suites_de_pruebas.png` | Ejecución de las 4 suites: 775 pruebas, 0 fallos (15 de octubre de 2026) | E4 |
| A-7 | `A-7_Commits_por_actividad.png` | Trazabilidad del trabajo en el repositorio | — |
| A-8 | `A-8_Resumen_reporte_auditoria.png` | Hallazgos de la auditoría corregidos y pendientes | — |
| B-1 | `B-1_Tablero_Kanban.png` | Backlog priorizado y tareas por estado | Metodología |
| B-2 | `B-2_Actas_revision_y_retrospectiva.png` | Revisión y retrospectiva de los sprints 1 a 4 | Metodología |
| B-3 | `B-3_Correo_docente_reuniones_diarias.png` | Coordinación de reuniones diarias con la docente | Metodología |
