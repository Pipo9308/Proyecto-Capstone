/**
 * Escapa texto para insertarlo en un documento HTML armado como string.
 *
 * Titulo, descripcion y agente de las alertas vienen de sitios externos
 * scrapeados (no confiables). Si un reporte se escribe con document.write en
 * una ventana del mismo origen, un HTML embebido podria leer el token de
 * localStorage.
 */
export function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
