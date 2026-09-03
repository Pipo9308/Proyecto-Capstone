# ENCI-INTEL — Proyecto Capstone

Proyecto de continuidad de software para **Encipharm**, empresa con más de 25 años en salud, nutrición y bioseguridad animal. ENCI-INTEL es una plataforma de agentes de IA (dashboard, alertas, agentes de scraping y consulta) construida sobre una base de código y arquitectura heredadas de una cohorte anterior.

Este repositorio reúne la documentación formal de la **Fase 1** de la asignatura Capstone: guía de definición de proyecto, diarios de reflexión, autoevaluaciones, diagnóstico técnico, informe final y presentación.

## Equipo

| Integrante | Foco |
|---|---|
| Felipe Ramos | Desarrollo de software (backend) |
| Benjamín Pumarino | Integración de sistemas y APIs / Aseguramiento de la calidad |
| Elías Sánchez | Análisis de datos e IA aplicada |

**Empresa mandante:** Encipharm (relación gestionada por Alloxentric, Product Owner: Max Kreimerman).

## Contenido de `documentos/`

| Archivo | Descripción |
|---|---|
| `1.5_Definicion_Proyecto_APT_Enci-Intel.pdf` | Guía de Definición de Proyecto APT presentada en Fase 1. |
| `1_1_APT122_AutoevaluacionCompetenciasFase1_FelipeRamos.pdf` | Autoevaluación de competencias — Felipe Ramos. |
| `AutoevaluacionCompetenciasBenjaminPumarino.pdf` | Autoevaluación de competencias — Benjamín Pumarino. |
| `1_2_APT122_DiarioReflexionFase1_FelipeRamos.pdf` | Diario de reflexión Fase 1 — Felipe Ramos. |
| `1_2_APT122_DiarioReflexionFase1_EliasSanchez (1).pdf` | Diario de reflexión Fase 1 — Elías Sánchez. |
| `DiarioReflexionFase1BenjaminPumarino.pdf` | Diario de reflexión Fase 1 — Benjamín Pumarino. |
| `DiarioReflexionFase1EliasSanchez.pdf` | Diario de reflexión Fase 1 — Elías Sánchez (versión final). |
| `Informe_EnciIntel_Fase1_final.docx` | Informe completo de Fase 1 (contexto, objetivos, metodología, riesgos, plan de trabajo). |
| `Enci-Intel_Fase1_Presentacion_2.pptx` | Presentación de cierre de Fase 1. |

## Resumen de Fase 1

Fase 1 se centró en levantar y diagnosticar el estado real del MVP heredado, en lugar de asumir brechas genéricas. El **2 de septiembre de 2026** el equipo realizó un diagnóstico técnico independiente sobre el código fuente, con estos resultados:

- **27 hallazgos priorizados P0–P3**, cada uno con archivo y línea de referencia.
- **3 hallazgos críticos de seguridad (P0)**: endpoints de lectura sin autenticación, reglas de `firestore.rules` mal versionadas y región del Cloud Scheduler mal codificada.
- Alcance formalmente aceptado (Acta de Entrega y Conformidad, 9 de julio de 2026): Dashboard + Alertas, Agente SAG, Agente Lanzamientos, Consultor Vet IA y Panel Admin — no el diseño original de 5 agentes ampliados.

Ese diagnóstico es la base de los objetivos, la metodología, la tabla de riesgos (incluye un riesgo **Alto** por los 3 hallazgos P0 de seguridad) y el plan de trabajo del informe de Fase 1.

**Stack actual:** React + TypeScript, FastAPI/Python, Firebase Authentication, Gemini 2.5 Flash / Groq como IA generativa; infraestructura en GCP (Cloud Run, Cloud Scheduler, Cloud Tasks, Firestore, Secret Manager).

## Próximos pasos hacia Fase 2

El plan de trabajo se organiza en 18 semanas: **Fase 1 (S1–S6)** corrección de hallazgos críticos, **Fase 2 (S7–S15)** endurecimiento y ampliación, **Fase 3 (S16–S18)** cierre y validación.

1. **Corregir de inmediato los 3 hallazgos P0** (autenticación en endpoints de lectura, `firestore.rules`, región del Cloud Scheduler) — ya diagnosticados y priorizados, listos para implementarse desde la semana 1.
2. **Continuar con las correcciones P1–P2** según el plan de trabajo y la Carta Gantt: embeddings multilingües y reindexado del corpus, reemplazo del pickle del vector store, rate limiter y caché compartidos entre instancias, unificación del campo `rol`, endurecimiento de los agentes de scraping y filtrado de alertas por vigencia/idioma.
3. **Ampliar la cobertura de pruebas** (safety scan, smoke tests de frontend, pruebas end-to-end) e integrar los cambios en el pipeline de CI/CD.
4. **Validar con Encipharm y Alloxentric** el cierre de las brechas priorizadas, y proponer las funcionalidades de Fase 2 originalmente planteadas en la Guía APT (Análisis de Productos, Mapa Competitivo) como mejora opcional posterior, no como brecha pendiente.

Hitos clave del plan: **S2** hallazgos P0 corregidos · **S5** vector store seguro y caché compartido · **S7** scraping endurecido y alertas filtradas · **S10** cobertura de pruebas y CI/CD actualizado · **S18** cierre, demo final y validación con la empresa mandante.

## Cómo revisar la documentación

El informe completo (`Informe_EnciIntel_Fase1_final.docx`) contiene el detalle de cada sección — contexto, vínculo con el perfil de egreso, factibilidad, objetivos, metodología, evidencias, plan de trabajo con Carta Gantt y referencias. La presentación (`Enci-Intel_Fase1_Presentacion_2.pptx`) resume estos mismos puntos para la exposición oral.
