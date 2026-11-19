export const perUnit = (value, unit) =>
  value == null ? "—" : `$${Number(value).toLocaleString("es-CL", { maximumFractionDigits: 2 })} / ${unit ?? ""}`.trim();

export function formatDiff(pct) {
  if (pct == null) return "—";
  return `${pct > 0 ? "+" : ""}${pct.toLocaleString("es-CL", { maximumFractionDigits: 2 })}%`;
}

// Diferencia de Encipharm: negativo = Encipharm mas barato que el competidor.
export const diffClass = (pct) => (pct == null ? "similar" : pct < 0 ? "mejor" : pct > 0 ? "peor" : "similar");
