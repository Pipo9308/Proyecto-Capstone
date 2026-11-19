// Las fechas de Intel son UTC; si llegan sin zona se asumen UTC (no hora local).
export function parseUtc(value) {
  if (!value) return null;
  const text = String(value);
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(text);
  const date = new Date(hasZone ? text : `${text}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatAlertDate(value) {
  const date = parseUtc(value);
  return date ? date.toLocaleDateString("es-CL", { day: "2-digit", month: "2-digit", year: "numeric" }) : "";
}

const PRIORITY = { critical: "Crítica", high: "Alta", medium: "Media", low: "Baja" };
export const priorityLabel = (priority) => PRIORITY[String(priority || "").toLowerCase()] || "Baja";

export const REGULACION = "Regulación";

/** Filtros del feed: "Todas", cada competidor que aparece en las alertas y "Regulación". */
export function buildAlertFilters(alerts) {
  const competitors = [...new Set(alerts.map((a) => a.competitor).filter(Boolean))].sort((a, b) => a.localeCompare(b, "es"));
  return ["Todas", ...competitors, REGULACION];
}

export function filterAlerts(alerts, filter) {
  if (filter === "Todas") return alerts;
  if (filter === REGULACION) return alerts.filter((a) => String(a.type || "").toUpperCase() === "REGULATORY");
  return alerts.filter((a) => a.competitor === filter);
}
