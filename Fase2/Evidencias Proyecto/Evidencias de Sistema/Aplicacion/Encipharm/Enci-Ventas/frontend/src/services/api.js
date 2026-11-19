import { clearAllCachedQueries } from "../hooks/useCachedQuery";

const DEFAULT_API_BASE_URL = "http://localhost:8000";

/**
 * Resolves the backend base URL from Vite environment variables.
 * The trailing slash is removed to keep endpoint composition stable.
 */
function getApiBaseUrl() {
  const configuredUrl = import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;
  return configuredUrl.replace(/\/+$/, "");
}

const API_BASE_URL = getApiBaseUrl();
const CLIENT_PLATFORM = "web";

export function clearApiGetCache() {
  // El cache real de queries vive en useCachedQuery (memoria + sessionStorage).
  // Debe limpiarse por completo al desloguear para no filtrar datos del
  // usuario anterior a la siguiente sesion en el mismo navegador/pestaña.
  clearAllCachedQueries();
}

function notifyDataMutated() {
  window.dispatchEvent(new CustomEvent("enci:data-mutated"));
}

export class ApiError extends Error {
  constructor(message, status, details = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = details.code || `API_HTTP_${status || "UNKNOWN"}`;
    this.details = details;
  }
}

function notifyAuthExpired(status) {
  if (status === 401) {
    window.dispatchEvent(new CustomEvent("enci:auth-expired"));
  }
}

function buildDiagnosticMessage({ code, message, method, path, status, traceId, upstreamStatus }) {
  const parts = [
    `[${code}]`,
    message,
    `Metodo: ${method}`,
    `Ruta: ${path}`,
  ];

  if (status) parts.push(`HTTP: ${status}`);
  if (upstreamStatus) parts.push(`Backend: ${upstreamStatus}`);
  if (traceId) parts.push(`Trace: ${traceId}`);

  return parts.join(" | ");
}

async function readErrorBody(response) {
  const text = await response.text().catch(() => "");
  if (!text) return { raw: "" };

  try {
    return JSON.parse(text);
  } catch {
    return {
      code: "API_ERROR_BODY_NOT_JSON",
      detail: "El servidor respondio con un cuerpo no JSON.",
      raw: text.slice(0, 500),
    };
  }
}

function getErrorDetail(errorBody) {
  if (Array.isArray(errorBody.detail)) {
    return errorBody.detail.map((item) => item.msg || JSON.stringify(item)).join(" ");
  }

  const details = [];
  if (errorBody.detail) details.push(errorBody.detail);
  if (errorBody.detalles && typeof errorBody.detalles === "object") {
    Object.entries(errorBody.detalles).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") details.push(`${key}: ${value}`);
    });
  }
  if (errorBody.message) details.push(errorBody.message);
  if (typeof errorBody.error === "string") details.push(errorBody.error);
  if (errorBody.hint) details.push(`Hint: ${errorBody.hint}`);
  if (errorBody.proxy?.attempts) details.push(`Intentos: ${errorBody.proxy.attempts}`);
  if (errorBody.error && typeof errorBody.error === "object") {
    const proxyError = [errorBody.error.name, errorBody.error.message].filter(Boolean).join(": ");
    if (proxyError) details.push(`ProxyError: ${proxyError}`);
    if (errorBody.error.cause) details.push(`Cause: ${errorBody.error.cause}`);
  }

  return details.join(" | ");
}

export async function apiFetch(path, { token, ...options } = {}) {
  const method = String(options.method || "GET").toUpperCase();

  const headers = {
    "X-Enci-Client": CLIENT_PLATFORM,
    ...(options.headers || {}),
  };

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response;
  const url = `${API_BASE_URL}${path}`;

  try {
    response = await fetch(url, {
      ...options,
      headers,
      cache: method === "GET" ? "no-store" : "default",
    });
  } catch (networkError) {
    const code = "API_NETWORK_FETCH_FAILED";
    throw new ApiError(
      buildDiagnosticMessage({
        code,
        message: "El navegador no pudo ejecutar fetch. Posible CORS, DNS, conexion o bloqueo de red.",
        method,
        path,
      }),
      0,
      {
        code,
        method,
        path,
        url,
        errorName: networkError?.name,
        errorMessage: networkError?.message,
      },
    );
  }

  if (!response.ok) {
    const errorBody = await readErrorBody(response);
    const traceId = response.headers.get("X-Enci-Trace-Id") || errorBody.traceId;
    const upstreamStatus = response.headers.get("X-Enci-Upstream-Status");
    const code = errorBody.code || errorBody.codigo || `API_HTTP_${response.status}`;
    const detail = getErrorDetail(errorBody);
    const message = buildDiagnosticMessage({
      code,
      message: detail || response.statusText || `Error ${response.status}`,
      method,
      path,
      status: response.status,
      traceId,
      upstreamStatus,
    });
    notifyAuthExpired(response.status);
    throw new ApiError(message, response.status, {
      code,
      method,
      path,
      url,
      traceId,
      upstreamStatus,
      body: errorBody,
    });
  }

  // 204 No Content (p. ej. DELETE /clientes/{id}) no trae cuerpo: no es un error.
  if (response.status === 204) {
    if (method !== "GET") {
      notifyDataMutated();
    }
    return null;
  }

  let data;
  try {
    data = await response.json();
  } catch (parseError) {
    const code = "API_SUCCESS_BODY_NOT_JSON";
    throw new ApiError(
      buildDiagnosticMessage({
        code,
        message: "La respuesta fue exitosa, pero no se pudo parsear como JSON.",
        method,
        path,
        status: response.status,
        traceId: response.headers.get("X-Enci-Trace-Id"),
      }),
      response.status,
      {
        code,
        method,
        path,
        url,
        errorMessage: parseError?.message,
      },
    );
  }
  if (method !== "GET") {
    notifyDataMutated();
  }

  return data;
}

export function loginWithCredentials(email, password) {
  return apiFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function registerWithCredentials(email, password) {
  return apiFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

// Invitaciones y restablecimiento de contraseña (enlace de un solo uso, RQ-05).
export function getInvitationPreview(token) {
  return apiFetch(withQuery("/auth/invitacion", { token }));
}

export function setPasswordWithToken(token, password) {
  return apiFetch("/auth/set-password", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
}

export function forgotPassword(email) {
  return apiFetch("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export function generateUserInvitation(token, uid) {
  return apiFetch(`/users/${uid}/invitacion`, { method: "POST", token });
}



export function updateCurrentUserPreferences(token, preferences) {
  return apiFetch("/users/me/preferences", {
    method: "PATCH",
    token,
    body: JSON.stringify(preferences),
  });
}

export function getCurrentUser(token) {
  return apiFetch("/users/me", { token });
}

export function getClientes(token, params = {}) {
  return apiFetch(withQuery("/clientes", { limit: 500, ...params }), { token });
}

export function getCliente(token, clienteId) {
  return apiFetch(`/clientes/${clienteId}`, { token });
}

export function createCliente(token, cliente) {
  return apiFetch("/clientes", {
    method: "POST",
    token,
    body: JSON.stringify(cliente),
  });
}

export function updateCliente(token, clienteId, cliente) {
  return apiFetch(`/clientes/${clienteId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(cliente),
  });
}

export async function deleteCliente(token, clienteId) {
  await apiFetch(`/clientes/${clienteId}`, {
    method: "DELETE",
    token,
  });
}


export function getDashboardVendedor(token) {
  return apiFetch("/dashboard/vendedor", { token });
}

export function getDashboardSupervisor(token) {
  return apiFetch("/dashboard/supervisor", { token });
}

export function getUsers(token, params = {}) {
  return apiFetch(withQuery("/users/", params), { token });
}

export function createUser(token, user) {
  return apiFetch("/users/", {
    method: "POST",
    token,
    body: JSON.stringify(user),
  });
}

export function setUserPassword(token, uid, password) {
  return apiFetch(`/users/${uid}/password`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ password }),
  });
}

export function updateUserRole(token, uid, rol) {
  return apiFetch(`/users/${uid}/role`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ rol }),
  });
}

export function updateUser(token, uid, changes) {
  return apiFetch(`/users/${uid}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(changes),
  });
}

export function updateUserStatus(token, uid, activo) {
  return apiFetch(`/users/${uid}/status`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ activo }),
  });
}

function withQuery(path, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, value);
    }
  });
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}

export function getInteracciones(token, params = {}) {
  return apiFetch(withQuery("/interacciones", params), { token });
}

export function createInteraccion(token, interaccion) {
  return apiFetch("/interacciones", {
    method: "POST",
    token,
    body: JSON.stringify(interaccion),
  });
}

export function getOportunidades(token, params = {}) {
  return apiFetch(withQuery("/oportunidades", { limit: 500, ...params }), { token });
}

export function getOportunidadDetalle(token, oportunidadId) {
  return apiFetch(`/oportunidades/${oportunidadId}/detalle`, { token });
}

export function createOportunidad(token, oportunidad) {
  return apiFetch("/oportunidades", {
    method: "POST",
    token,
    body: JSON.stringify(oportunidad),
  });
}

export function updateOportunidad(token, oportunidadId, oportunidad) {
  return apiFetch(`/oportunidades/${oportunidadId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(oportunidad),
  });
}

export function getPropuestas(token, params = {}) {
  return apiFetch(withQuery("/propuestas", { limit: 500, ...params }), { token });
}


export function sendRagMessage(token, payload) {
  return apiFetch("/rag/chat", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function getRagConversations(token) {
  return apiFetch("/rag/conversations", { token });
}

export function getRagDocuments(token) {
  return apiFetch("/rag/documents", { token });
}

export async function uploadRagDocument(token, file) {
  const formData = new FormData();
  formData.append("file", file);

  return apiFetch("/rag/documents/upload", {
    method: "POST",
    token,
    body: formData,
  });
}

export function deleteRagDocument(token, documentId) {
  return apiFetch(`/rag/documents/${documentId}`, { method: "DELETE", token });
}

export function reindexRagDocuments(token) {
  return apiFetch("/rag/documents/reindex", {
    method: "POST",
    token,
  });
}

// ── Adjuntos de propuestas (RQ-07) ─────────────────────────────────────────────

/** URL absoluta para un camino devuelto por la API (p. ej. el enlace firmado de descarga). */
export function buildApiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

export function getPropuestaArchivos(token, propuestaId) {
  return apiFetch(`/propuestas/${propuestaId}/archivos`, { token });
}

export function getPropuestaArchivoLink(token, propuestaId, archivoId) {
  return apiFetch(`/propuestas/${propuestaId}/archivos/${archivoId}/enlace`, { token });
}

export function deletePropuestaArchivo(token, propuestaId, archivoId) {
  return apiFetch(`/propuestas/${propuestaId}/archivos/${archivoId}`, { method: "DELETE", token });
}

/**
 * Sube un archivo mostrando el avance (fetch no informa el progreso de subida).
 * Rechaza con ApiError igual que apiFetch, con el cuerpo del backend en `details.body`.
 */
export function uploadFileWithProgress(path, { token, file, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const url = `${API_BASE_URL}${path}`;
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.setRequestHeader("X-Enci-Client", CLIENT_PLATFORM);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) onProgress(Math.round((event.loaded * 100) / event.total));
    };
    xhr.onload = () => {
      let body;
      try {
        body = JSON.parse(xhr.responseText || "{}");
      } catch {
        body = { raw: String(xhr.responseText || "").slice(0, 200) };
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        notifyDataMutated();
        resolve(body);
        return;
      }
      notifyAuthExpired(xhr.status);
      const code = body.codigo || body.code || `API_HTTP_${xhr.status}`;
      const message = buildDiagnosticMessage({
        code,
        message: typeof body.error === "string" ? body.error : (body.detail || xhr.statusText || `Error ${xhr.status}`),
        method: "POST",
        path,
        status: xhr.status,
      });
      reject(new ApiError(message, xhr.status, { code, method: "POST", path, url, body }));
    };
    xhr.onerror = () => {
      const code = "API_NETWORK_FETCH_FAILED";
      reject(new ApiError(
        buildDiagnosticMessage({ code, message: "No se pudo conectar con el servidor.", method: "POST", path }),
        0,
        { code, method: "POST", path, url },
      ));
    };
    const formData = new FormData();
    formData.append("file", file);
    xhr.send(formData);
  });
}

export function uploadPropuestaArchivo(token, propuestaId, file, onProgress) {
  return uploadFileWithProgress(`/propuestas/${propuestaId}/archivos`, { token, file, onProgress });
}

export function createPropuesta(token, propuesta) {
  return apiFetch("/propuestas", {
    method: "POST",
    token,
    body: JSON.stringify(propuesta),
  });
}

export function updatePropuesta(token, propuestaId, propuesta) {
  return apiFetch(`/propuestas/${propuestaId}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(propuesta),
  });
}

export function getAlertas(token, params = {}) {
  return apiFetch(withQuery("/inteligencia/alertas", params), { token });
}

export function askCompetenciaChat(token, payload) {
  return apiFetch("/inteligencia/competencia-chat", { method: "POST", token, body: JSON.stringify(payload) });
}

// ── Competencia (RQ-04) ──────────────────────────────────────────────────────

export function getCompetenciaCatalogo(token) {
  return apiFetch("/competencia/catalogo", { token });
}

export function getCompetenciaComparativa(token, productoEncipharmId) {
  return apiFetch(withQuery("/competencia/comparativa", { productoEncipharmId }), { token });
}

export function getCompetenciaResumen(token) {
  return apiFetch("/competencia/resumen", { token });
}

export function getCompetenciaProductos(token, params = {}) {
  return apiFetch(withQuery("/competencia/productos", params), { token });
}

export function createCompetenciaProducto(token, producto) {
  return apiFetch("/competencia/productos", { method: "POST", token, body: JSON.stringify(producto) });
}

export function reportarPrecioCompetencia(token, productoId, precio) {
  return apiFetch(`/competencia/productos/${encodeURIComponent(productoId)}/precios`, {
    method: "POST",
    token,
    body: JSON.stringify(precio),
  });
}

export function getPreciosCompetencia(token, params = {}) {
  return apiFetch(withQuery("/competencia/precios", params), { token });
}

export function revisarPrecioCompetencia(token, precioId, aprobar) {
  return apiFetch(`/competencia/precios/${encodeURIComponent(precioId)}/${aprobar ? "aprobar" : "descartar"}`, {
    method: "POST",
    token,
  });
}


export function createCatalogoProducto(token, producto) {
  return apiFetch("/competencia/catalogo", { method: "POST", token, body: JSON.stringify(producto) });
}

export function setCompetenciaEquivalentes(token, productoId, encipharmIds) {
  return apiFetch(`/competencia/productos/${encodeURIComponent(productoId)}/equivalentes`, {
    method: "PUT",
    token,
    body: JSON.stringify({ encipharmIds }),
  });
}

// ── Metas mensuales ──────────────────────────────────────────────────────────

export function getMetas(token, mes) {
  return apiFetch(withQuery("/metas", { mes }), { token });
}

export function putMeta(token, body) {
  return apiFetch("/metas", { method: "PUT", token, body: JSON.stringify(body) });
}

// ── Notificaciones (RQ-01) ───────────────────────────────────────────────────

export function getNotificaciones(token, params = {}) {
  return apiFetch(withQuery("/notificaciones", params), { token });
}

export function marcarNotificacionLeida(token, id) {
  return apiFetch(`/notificaciones/${encodeURIComponent(id)}/leida`, { method: "PATCH", token });
}

export function marcarTodasNotificaciones(token) {
  return apiFetch("/notificaciones/marcar-todas", { method: "POST", token });
}

// ── Calendario (RQ-02) ───────────────────────────────────────────────────────

export function getEventos(token, params = {}) {
  return apiFetch(withQuery("/eventos", params), { token });
}

export function createEvento(token, evento) {
  return apiFetch("/eventos", { method: "POST", token, body: JSON.stringify(evento) });
}

export function updateEvento(token, id, cambios) {
  return apiFetch(`/eventos/${encodeURIComponent(id)}`, { method: "PATCH", token, body: JSON.stringify(cambios) });
}
