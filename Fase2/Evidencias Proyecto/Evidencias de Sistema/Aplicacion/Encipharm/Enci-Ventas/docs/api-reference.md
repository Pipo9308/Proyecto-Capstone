# Enci Ventas - API Reference

Base URL: `http://127.0.0.1:8000` (Desarrollo) / Configurable vía variables de entorno en Producción.

Todos los endpoints protegidos requieren el siguiente encabezado HTTP:

```http
Authorization: Bearer <jwt_token>
```

El token JWT se obtiene al autenticarse y contiene la identidad del usuario y sus permisos básicos.

## 1. Autenticación y Autorización

### Errores estándar
Los errores HTTP se normalizan con el siguiente contrato JSON:
```json
{
  "error": "Mensaje de error",
  "codigo": "ERR_CODE",
  "detalles": null,
  "timestamp": "2026-05-15T12:00:00+00:00"
}
```
*Códigos comunes: `ERR_BAD_REQUEST`, `ERR_UNAUTHORIZED`, `ERR_FORBIDDEN`, `ERR_NOT_FOUND`, `ERR_VALIDATION`, `ERR_INTERNAL`.*

### `POST /auth/login`
Autentica al usuario usando credenciales propias (email y contraseña bcrypt) y retorna un JWT.

### `GET /me`
Retorna los datos básicos del usuario autenticado a partir del token JWT.

### `GET /health`
Verifica que el servidor esté operativo. (Retorna `{"status": "ok"}`).

## 2. Usuarios y Roles

| Rol | Alcance |
|-----|---------|
| `sin_acceso` | Cuenta creada, pero pendiente de aprobación administrativa. |
| `admin` | Puede listar, consultar y modificar usuarios, roles y estado. |
| `supervisor` | Puede listar y consultar usuarios, aprueba propuestas. |
| `vendedor` | No puede administrar usuarios, solo ve sus datos y clientes. |

### Endpoints
- **`GET /users/`**: Lista usuarios (Filtros: `activo`, `limit`). Req: `admin`, `supervisor`.
- **`GET /users/{uid}`**: Retorna usuario por UID. Req: `admin`, `supervisor`.
- **`PATCH /users/{uid}`**: Actualiza datos administrativos (nombre, activo). Req: `admin`.
- **`PATCH /users/{uid}/role`**: Actualiza el rol (`sin_acceso`, `vendedor`, `supervisor`, `admin`). Req: `admin`.
- **`PATCH /users/{uid}/status`**: Activa o desactiva usuario. Req: `admin`.

## 3. Clientes (CRM)

### Endpoints
- **`GET /clientes/`**: Lista clientes con filtros (`search`, `estado`, `vendedorUid`, `limit`). Req: Todos. *Vendedores solo ven sus clientes.*
- **`POST /clientes/`**: Crea un cliente.
- **`PATCH /clientes/{cliente_id}`**: Actualiza un cliente.
- **`DELETE /clientes/{cliente_id}`**: Baja lógica de un cliente (estado Inactivo, fecha `deletedAt`).
- **`POST /clientes/import-csv`**: Importa clientes vía CSV (`multipart/form-data`). Req: `admin`. Valida formato UTF-8 y rechaza correos duplicados.

## 4. Flujo Comercial (Interacciones, Oportunidades, Propuestas)

### Interacciones
- **`GET /interacciones`**: Lista interacciones (Filtros: `clienteId`, `limit`).
- **`POST /interacciones`**: Registra interacción (`llamada`, `visita`, `correo`, `reunion`).

### Oportunidades (Pipeline)
- **`GET /oportunidades`**: Lista oportunidades (Filtros: `clienteId`, `etapa`, `limit`).
- **`POST /oportunidades`**: Crea oportunidad en etapas: `nuevo`, `contactado`, `cotizacion`, `negociacion`, `ganado`, `perdido`.
- **`PATCH /oportunidades/{oportunidad_id}`**: Actualiza etapa o datos.
- **`GET /oportunidades/{oportunidad_id}/detalle`**: Oportunidad con últimas interacciones y propuestas.

### Propuestas
- **`GET /propuestas`**: Lista propuestas (Filtros: `clienteId`, `oportunidadId`, `estado`, `limit`).
- **`POST /propuestas`**: Crea propuesta vinculada a oportunidad (`borrador`, `enviada`, `aceptada`, `rechazada`).
- **`PATCH /propuestas/{propuesta_id}`**: Actualiza estado o montos. *Supervisores solo aprueban (estado: aceptada).*

## 5. Dashboard

- **`GET /dashboard/vendedor`**: Métricas de clientes del vendedor autenticado.
- **`GET /dashboard/supervisor`**: Métricas consolidadas de todos los clientes y pipeline general. Req: `admin`, `supervisor`.
- *Respuesta incluye:* totales, desglose por estado, rubro, región, oportunidades y propuestas valorizadas.

## 6. Enci Chat (RAG AI)

- **`POST /rag/chat`**: Envía una pregunta semántica al asistente. Limite 1000 caracteres.
- **`GET /rag/conversations`**: Lista historial de chats del usuario.
- **`POST /rag/documents/upload`**: Carga/Indexa documento (`.pdf`, `.docx`, `.txt`). Req: `admin`.
- **`POST /rag/documents/reindex`**: Reconstruye el índice vectorial en base de datos. Req: `admin`.
- **`GET /rag/documents`**: Lista documentos activos en el RAG. Req: `admin`.

## 7. Competencia, notificaciones y calendario (Fase 4)

> Esta referencia aún no cubre los endpoints de las Fases 1–3 (`/inteligencia/*`, invitaciones, adjuntos, documentos RAG); ver `plan-integracion-ers.md`.

### Competencia (RQ-04) — prefijo `/competencia`

| Método y ruta | Rol mínimo | Qué hace |
|---|---|---|
| `GET /productos` | vendedor | Lista con filtros `competidor`, `categoria`, `principio`, `q` y paginación `page`/`pageSize` (máx. 100) en SQL. Incluye el último precio **aprobado** y los equivalentes Encipharm |
| `POST /productos` | vendedor | Registra un producto de la competencia (409 si ya existe mismo competidor + nombre + presentación) |
| `GET /productos/{id}` | vendedor | Detalle con historial de precios (un vendedor ve los aprobados y los suyos) |
| `PATCH /productos/{id}` · `PUT /productos/{id}/equivalentes` | supervisor | Edita; reemplaza la lista de equivalentes con el catálogo Encipharm |
| `DELETE /productos/{id}` | admin | Borra el producto con sus precios y equivalencias |
| `POST /productos/{id}/precios` | vendedor | Reporta un precio (nuevo registro; nada se pisa). Del vendedor queda `pendiente`; de supervisor/admin, `aprobado` |
| `GET /precios` | supervisor | Cola de revisión (`estado` por defecto `pendiente`) |
| `POST /precios/{id}/aprobar` · `/descartar` | supervisor | Revisa un reporte pendiente (409 si ya estaba revisado) |
| `GET /comparativa?productoEncipharmId=` | vendedor | Equivalentes del producto con precio por unidad y `diferenciaPct` = (Encipharm − competidor) / competidor × 100; si no se puede calcular, `motivoSinDiferencia` |
| `GET /resumen` | vendedor | Promedios por categoría y por competidor (por unidad de medida y moneda) |
| `GET/POST/PATCH/DELETE /catalogo` | lectura vendedor, escritura supervisor, borrado admin | Catálogo mínimo de productos Encipharm |

### Notificaciones (RQ-01) — prefijo `/notificaciones`

| Método y ruta | Qué hace |
|---|---|
| `GET /notificaciones?soloNoLeidas&limit&offset` | Avisos del usuario más `noLeidas`. Dispara en segundo plano el sondeo de alertas de Intel, los recordatorios de visitas y la purga de 90 días |
| `PATCH /notificaciones/{id}/leida` | Marca una (204; 404 si es de otro usuario) |
| `POST /notificaciones/marcar-todas` | Marca todas las del usuario |

Variables: `NOTIFICATIONS_INTEL_POLL_SECONDS` (120; 0 apaga el sondeo) y `NOTIFICATIONS_INTEL_LOOKBACK_HOURS` (72).

### Calendario (RQ-02) — prefijo `/eventos`

| Método y ruta | Qué hace |
|---|---|
| `GET /eventos?desde&hasta&vendedorUid&clienteId&estado` | Eventos que se cruzan con el rango (máx. 93 días). Un vendedor solo recibe los suyos; supervisor/admin todos o filtrados |
| `POST /eventos` | Crea (cliente obligatorio y visible para el usuario; oportunidad opcional del mismo cliente; máx. 12 h). Supervisor/admin pueden indicar `vendedorUid` y a este le llega un aviso |
| `PATCH /eventos/{id}` | Edita, mueve, cancela o marca `realizada` (crea la interacción en el historial del cliente, una sola vez). Un evento realizado o cancelado ya no se mueve (409) |

Las horas viajan y se guardan en UTC. Los avisos de 24 h y 1 h llegan por `/notificaciones`.

## 8. Auditoría y trazabilidad (Fase 5)

- **`GET /auditoria`** (solo admin): registros de auditoría, más nuevos primero. Filtros `desde`, `hasta`, `usuario` (uid), `recurso` (primer segmento de la ruta, p. ej. `clientes`), `resultado` (`success`, `denied`, `failure`, `error`) y paginación `limit` (máx. 200) / `offset`. Cada registro trae `timestamp` (ISO 8601 UTC con milisegundos), `userUid`, `userRole`, `method`, `route` (plantilla), `resourceId`, `statusCode`, `result`, `ip`, `userAgent`, `client` y `details` (p. ej. el correo de un intento de login). No existe forma de editar ni borrar registros.
- Se auditan `POST`, `PUT`, `PATCH` y `DELETE` más la descarga de archivos con enlace firmado. No se auditan los avisos, las alertas de Intel ni las preguntas al chat.
- Toda respuesta trae `X-Request-ID` (se respeta el que envíe el cliente si es seguro) para seguir una petición en los logs.
- `GET /readiness` exige sesión de admin; `GET /` ya no existe. Solo `/health` y los endpoints de acceso a la cuenta son públicos.
