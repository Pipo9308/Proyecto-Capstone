/**
 * El backend devuelve el rol canonico ("admin", "gerencia", "comercial", "pendiente").
 * La interfaz usa "administrador" para el rol de administracion: se traduce en un
 * solo punto (aqui) para no repartir comparaciones por todo el codigo.
 */
export function toUiRole(role: unknown): "administrador" | "gerencia" | "comercial" | "pendiente" {
  const value = String(role ?? "").trim().toLowerCase();
  if (value === "admin" || value === "administrador") return "administrador";
  if (value === "gerencia" || value === "comercial") return value;
  return "pendiente";
}
