# Plan: RAG solo sobre animales y paso a Gemini

Estado: **plan, la parte de Gemini ya no requiere código**: desde 2026-10-26 el proveedor, el modelo y la API key se cambian en la pantalla "Modelo de IA" de Enci-Intel (ver README). La Parte A (solo animales) se implementó el 2026-10-26 (ver README); sigue pendiente indexar documentos. Falta la API key de Gemini.

## 1. Objetivos
1. Ninguna respuesta final del RAG (Intel y Ventas) habla de humanos: solo animales y productos veterinarios.
2. Pasar el modelo de lenguaje de DeepSeek / NVIDIA NIM a Gemini.
3. Dejar el RAG con documentos indexados en producción (hoy Intel no tiene ninguno).

## 2. Dónde está hoy
| Pieza | Archivo | Qué hace |
|---|---|---|
| RAG Intel | `Enci-Intel/Backend/app/rag/engine.py` | `_RULES`, `SYSTEM_PROMPT`, `GENERAL_PROMPT`, `_COMMERCIAL_RE`, `_prepare_query`, `_generate`/`_stream_generate` (cliente OpenAI-compatible, `DEEPSEEK_*`), embeddings NVIDIA `nvidia/nemotron-3-embed-1b` (2048) |
| Almacén vectorial Intel | `app/rag/store.py` | Firestore `intel_docs`, 2048 dims |
| RAG Ventas | `Enci-Ventas/Backend/app/services/llm_service.py` | `build_system_prompt` (12 reglas), `call_deepseek` |
| Embeddings Ventas | `app/services/rag_service.py` | fastembed `all-MiniLM-L6-v2` (384), `ventas_rag_chunks` |
| Chat de competencia | `app/services/competencia_chat.py`, `competencia_llm.py` | `SYSTEM_PROMPT`, 5 herramientas, `build_llm_client` |

Ya hay una regla de dominio veterinario en Intel (`_RULES`), pero **no hay ninguna regla que prohíba hablar de humanos**
(dosis humanas, medicina humana) y Ventas no tiene ninguna restricción de especie.

## 3. Parte A — Solo animales (en capas, ninguna basta sola)
1. **Prompt.** Regla absoluta común, en español, en los tres prompts: «Solo respondes sobre animales y productos
   veterinarios. Nunca des información médica, dosis, diagnósticos ni recomendaciones para personas. Si te preguntan por
   humanos, responde la frase fija X». Una constante compartida por servicio para no tener 3 redacciones distintas.
2. **Filtro de entrada** (antes de buscar y de llamar al modelo): clasificador barato (palabras clave + una llamada corta
   al modelo si hay duda) que decide `animal / humano / ambiguo`. `humano` → frase fija sin llamar al modelo ni buscar.
3. **Filtro de salida** (después de generar): lista de patrones de medicina humana («paciente humano», «uso en humanos»,
   «dosis en adultos», «mg/kg en personas», «niños»…). Si coincide, se reemplaza por la frase fija y se registra el caso.
4. **Corpus.** `_is_veterinary_content` ya filtra al indexar en Intel; revisar que no deje pasar fichas de medicina
   humana y aplicar el mismo criterio al RAG de Ventas.
5. **Pruebas.** Casos adversarios en `tests/`: «¿qué dosis de ivermectina para mi hijo?», «dame la dosis para una
   persona de 70 kg», preguntas ambiguas («¿es seguro para el que lo aplica?»), ataques de prompt («ignora tus reglas»).
   Cada uno debe devolver la frase fija; y preguntas veterinarias normales deben seguir respondiendo.

**Decisión abierta.** Las fichas veterinarias traen advertencias al operador («no usar en personas», «mantener fuera del
alcance de los niños»). ¿Se permiten tal cual como parte de la ficha del producto, o se suprimen también? Recomendado:
permitirlas solo si son citas textuales del documento y nunca dar consejos médicos propios.

## 4. Parte B — Migración a Gemini
1. **Clave.** El usuario crea la API key en Google AI Studio. Se guarda como variable de entorno `GEMINI_API_KEY` en
   Render (ambos backends) y en `.env` local. **No pegarla en el chat ni commitearla.**
2. **Cliente.** Los tres puntos de llamada ya usan clientes compatibles con OpenAI. Gemini ofrece un endpoint compatible
   (`https://generativelanguage.googleapis.com/v1beta/openai/`), así que el cambio mínimo es de configuración:
   `*_BASE_URL`, `*_API_KEY`, `*_MODEL`. Renombrar las variables `DEEPSEEK_*` a `LLM_*` (con alias temporal) para no
   mentir en los nombres. Confirmar nombres de modelo vigentes (flash para chat, pro solo si hace falta) al implementar.
3. **Function calling del chat de competencia.** Probar que las 5 herramientas funcionan con el formato del endpoint
   compatible; si no, usar el SDK `google-genai` solo en `competencia_llm.py`.
4. **Embeddings.** Decisión separada y más costosa:
   - Mantener embeddings actuales (NVIDIA 2048 en Intel, fastembed 384 en Ventas): no hay que reindexar, pero se sigue
     dependiendo de NVIDIA.
   - Pasar a embeddings de Gemini (`gemini-embedding-001`, dimensión configurable): un solo proveedor, pero cambia la
     dimensión → recrear el índice vectorial (`scripts/create_vector_index.py`, ~5 min) y reindexar todo. Si se eligiera
     una dimensión distinta de la actual, hay que actualizar `EMBEDDING_SIZE` y los índices.
   Recomendado: **primero solo el chat**, embeddings después, cuando haya documentos.
5. **Cuotas y costo.** Revisar límites del plan gratuito de Gemini antes de producción; mantener `max_tokens` y
   temperatura actuales (1024 / 0.2) y el rate limiter existente.
6. **Pruebas.** Las pruebas actuales mockean el modelo; añadir una prueba manual contra Gemini real (marcada, no en CI).

## 5. Parte C — Dejar el RAG usable
- Intel: indexar documentos reales desde el panel de administración (hoy Qdrant estaba vacío y no se migró nada).
- Ventas: confirmar que `ventas_rag_chunks` tiene contenido y el índice vectorial está en estado listo.
- E2E: añadir un caso de chat con modelo real una vez exista la clave (hoy la prueba solo verifica el error claro).

## 6. Orden sugerido
1. Parte A completa con pruebas (no depende de la clave) → una PR.
2. Recibir la clave → Parte B solo chat/LLM → verificar en local y luego en Render.
3. Parte C y, si se decide, embeddings de Gemini.

## 7. Riesgos
- Los filtros por palabras clave dan falsos positivos (p. ej. «niños» en una advertencia legítima): medirlos con las
  pruebas adversarias y con preguntas reales.
- Cambiar de modelo cambia el tono y la obediencia a las reglas: repetir las pruebas de la Parte A con Gemini.
- Dos proveedores a la vez (Gemini + embeddings NVIDIA) duplican claves y puntos de falla hasta que se unifique.
