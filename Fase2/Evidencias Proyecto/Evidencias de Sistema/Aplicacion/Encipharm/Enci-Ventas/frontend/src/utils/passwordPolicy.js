// Politica de contrasenas (misma que el backend, app/core/password_policy.py).
export const PASSWORD_MIN_LENGTH = 10;
export const PASSWORD_HINT = "Minimo 10 caracteres, con letras y numeros.";

/** Mensaje de error o "" si la contrasena cumple la politica. */
export function passwordPolicyError(password) {
  const value = String(password || "");
  if (value.length < PASSWORD_MIN_LENGTH) return `La contrasena debe tener al menos ${PASSWORD_MIN_LENGTH} caracteres.`;
  if (new TextEncoder().encode(value).length > 72) return "La contrasena es demasiado larga (maximo 72 bytes).";
  if (!/\p{L}/u.test(value) || !/\d/.test(value)) return "La contrasena debe incluir letras y numeros.";
  return "";
}
