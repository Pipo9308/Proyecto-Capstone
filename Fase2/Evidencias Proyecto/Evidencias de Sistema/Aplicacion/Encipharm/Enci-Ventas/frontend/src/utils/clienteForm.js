import { normalizeRut, rutError } from "./rut";

export const CLIENTE_ESTADOS = ["En proceso", "Completado", "Inactivo"];

// Obligatorios (igual que el backend): nombre del contacto, empresa, RUT e industria.
// Opcionales: email, telefono y region.
export const CLIENTE_REQUIRED_FIELDS = ["nombre", "empresa", "rut", "rubro"];

export const clienteInitialForm = {
  nombre: "",
  empresa: "",
  rut: "",
  email: "",
  telefono: "",
  rubro: "",
  region: "",
  estado: "En proceso",
  vendedorUid: "",
};

const textPattern = /^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ .,&'-]+$/;
const formulaPrefixes = ["=", "+", "-", "@"];
const fieldLimits = {
  nombre: 120,
  empresa: 160,
  telefono: 8,
  rubro: 120,
  region: 80,
};

function normalizeText(value) {
  return String(value || "").trim();
}

export function normalizeTelefono(value) {
  const digits = normalizeText(value).replace(/\D/g, "");
  if (digits.startsWith("569") && digits.length >= 11) {
    return digits.slice(3, 11);
  }
  if (digits.startsWith("9") && digits.length >= 9) {
    return digits.slice(1, 9);
  }
  return digits;
}

export function buildClientePayload(form) {
  const rut = normalizeText(form.rut);
  const payload = {
    nombre: normalizeText(form.nombre),
    empresa: normalizeText(form.empresa),
    rut: normalizeRut(rut) || rut,
    email: normalizeText(form.email).toLowerCase() || null,
    telefono: normalizeTelefono(form.telefono).slice(0, 8) || null,
    rubro: normalizeText(form.rubro),
    region: normalizeText(form.region) || null,
    estado: form.estado || "En proceso",
  };
  // Solo supervisor y admin eligen vendedor; para el resto el backend asigna al usuario.
  if (form.vendedorUid) payload.vendedorUid = form.vendedorUid;
  return payload;
}

/**
 * @param {object} form
 * @param {{requireRut?: boolean}} options  `requireRut: false` al editar un cliente anterior que aun no tiene RUT.
 */
export function validateClienteForm(form, { requireRut = true } = {}) {
  const payload = buildClientePayload(form);
  const errors = {};

  for (const field of ["nombre", "empresa", "rubro", "region"]) {
    const required = CLIENTE_REQUIRED_FIELDS.includes(field);
    if (!payload[field]) {
      if (required) errors[field] = "Campo obligatorio.";
    } else if (payload[field].length > fieldLimits[field]) {
      errors[field] = `Maximo ${fieldLimits[field]} caracteres.`;
    } else if (formulaPrefixes.some((prefix) => payload[field].startsWith(prefix))) {
      errors[field] = "No puede iniciar con caracteres de formula.";
    } else if (!textPattern.test(payload[field])) {
      errors[field] = "Usa solo letras, numeros y signos comerciales basicos.";
    }
  }

  const rutText = normalizeText(form.rut);
  if (rutText || requireRut) {
    const message = rutError(rutText);
    if (message) errors.rut = message;
  }

  if (payload.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payload.email)) {
    errors.email = "Ingresa un correo valido.";
  }

  const normalizedPhone = normalizeTelefono(form.telefono);
  if (normalizedPhone && normalizedPhone.length < fieldLimits.telefono) {
    errors.telefono = "Ingresa exactamente 8 digitos despues de +569.";
  }

  return {
    errors,
    isValid: Object.keys(errors).length === 0,
    payload: {
      ...payload,
      rut: payload.rut || null,
      telefono: normalizedPhone.slice(0, 8) || null,
    },
  };
}
