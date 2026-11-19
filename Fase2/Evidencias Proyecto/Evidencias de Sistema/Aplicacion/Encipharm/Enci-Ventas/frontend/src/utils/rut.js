// RUT chileno: misma regla que el backend (app/core/rut.py), para validar mientras se escribe.

export function computeDv(body) {
  let total = 0;
  let factor = 2;
  for (const digit of String(body).split("").reverse()) {
    total += Number(digit) * factor;
    factor = factor < 7 ? factor + 1 : 2;
  }
  const remainder = 11 - (total % 11);
  if (remainder === 11) return "0";
  if (remainder === 10) return "K";
  return String(remainder);
}

/** Devuelve el RUT canonico `12345678-5` o null si no es valido. */
export function normalizeRut(value) {
  const cleaned = String(value || "").replace(/[.\s-]/g, "").toUpperCase();
  if (!/^\d{7,8}[\dK]$/.test(cleaned)) return null;
  const body = cleaned.slice(0, -1);
  const dv = cleaned.slice(-1);
  if (computeDv(body) !== dv) return null;
  return `${Number(body)}-${dv}`;
}

/** Mensaje de error para un RUT escrito por el usuario ("" si es valido). */
export function rutError(value) {
  const cleaned = String(value || "").replace(/[.\s-]/g, "").toUpperCase();
  if (!cleaned) return "Campo obligatorio.";
  if (!/^\d{7,8}[\dK]$/.test(cleaned)) return "Ingresa un RUT valido, por ejemplo 12.345.678-5.";
  if (computeDv(cleaned.slice(0, -1)) !== cleaned.slice(-1)) return "El digito verificador del RUT no coincide.";
  return "";
}

/** Formato de lectura con puntos: 12.345.678-5. */
export function formatRut(value) {
  const normalized = normalizeRut(value);
  if (!normalized) return String(value || "");
  const [body, dv] = normalized.split("-");
  return `${body.replace(/\B(?=(\d{3})+(?!\d))/g, ".")}-${dv}`;
}
