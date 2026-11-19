// Convierte los errores del backend ({error, codigo, detalles}) en errores por campo del formulario.

const FRIENDLY = [
  [/field required|string should have at least 1 character|value is not a valid/i, null],
  [/valid email|not a valid email/i, "Ingresa un correo valido."],
];

function cleanMessage(message, field) {
  const text = String(message || "").replace(/^Value error,\s*/i, "");
  if (/field required|at least 1 character/i.test(text)) return "Campo obligatorio.";
  if (/email/i.test(text) && field === "email") return "Ingresa un correo valido.";
  for (const [pattern, replacement] of FRIENDLY) {
    if (replacement && pattern.test(text)) return replacement;
  }
  return text;
}

/**
 * - 422 de validacion: `detalles` es una lista [{loc, msg}] -> un error por campo.
 * - 409/422 del servicio: `detalles.campo` indica el campo y `error` el mensaje.
 */
export function fieldErrorsFromApi(error) {
  const body = error?.details?.body;
  const detalles = body?.detalles;
  const errors = {};

  if (Array.isArray(detalles)) {
    for (const item of detalles) {
      const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : null;
      if (typeof field === "string" && !errors[field]) errors[field] = cleanMessage(item.msg, field);
    }
  } else if (detalles && typeof detalles.campo === "string") {
    errors[detalles.campo] = typeof body.error === "string" ? body.error : "Valor no valido.";
  }
  return errors;
}
