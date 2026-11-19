export function getFriendlyApiError(error) {
  const message = error?.message || "";

  if (message.includes("Failed to fetch")) {
    return "No se pudo conectar con la API. Intenta nuevamente en unos segundos.";
  }

  if (message.includes("401") || message.toLowerCase().includes("token")) {
    return "Tu sesion expiro o el token no pudo validarse. Cierra sesion e ingresa nuevamente.";
  }

  if (message.includes("403") || message.toLowerCase().includes("permis")) {
    return "No tienes permisos para realizar esta accion.";
  }

  if (message.includes("429") || message.toLowerCase().includes("cuota") || message.toLowerCase().includes("quota")) {
    return "Se alcanzo el limite de solicitudes. Espera un momento e intenta nuevamente.";
  }

  if (message.includes("503") || message.toLowerCase().includes("temporalmente no disponible")) {
    return "El servicio de datos esta temporalmente no disponible. Intenta nuevamente en unos minutos.";
  }

  if (message.includes("422") || message.toLowerCase().includes("validation")) {
    return "Revisa los campos obligatorios y el formato del correo.";
  }

  if (message.includes("500")) {
    return "La API tuvo un problema al guardar. Intenta nuevamente o revisa el log del backend.";
  }

  return message || "No se pudo completar la solicitud.";
}

/** Mensaje que dio el backend (contrato `{error, codigo, ...}`) o, si no hay, uno generico. */
export function apiMessage(error) {
  const body = error?.details?.body;
  // Un 422 de validacion trae el motivo real en `detalles`; sin esto solo se veia "Datos de entrada invalidos".
  const reason = Array.isArray(body?.detalles) ? body.detalles.find((d) => d?.msg)?.msg : null;
  if (reason) return String(reason).replace(/^Value error,\s*/i, "");
  return body?.error || getFriendlyApiError(error);
}
