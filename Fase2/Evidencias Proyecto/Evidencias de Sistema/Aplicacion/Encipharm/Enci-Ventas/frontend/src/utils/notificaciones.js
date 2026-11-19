import { parseUtc } from "./alertas";

/** "hace 5 min", "hace 3 h", "hace 2 d"; pasados 30 dias, la fecha. */
export function timeAgo(value, now = new Date()) {
  const moment = parseUtc(value);
  if (!moment) return "";
  const minutes = Math.floor((now - moment) / 60000);
  if (minutes < 1) return "ahora";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `hace ${days} d`;
  return moment.toLocaleDateString("es-CL");
}

export const badgeText = (count) => (count > 99 ? "99+" : String(count));
