import { parseUtc } from "./alertas";

export const VIEWS = { mes: "Mes", semana: "Semana", dia: "Día" };

const pad = (n) => String(n).padStart(2, "0");

export const startOfDay = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());

export function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

/** Lunes de la semana de `date`. */
export function startOfWeek(date) {
  const day = startOfDay(date);
  return addDays(day, -((day.getDay() + 6) % 7));
}

/** Clave local "YYYY-MM-DD" de un dia. */
export const dayKey = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

/** Dias que muestra cada vista y el rango [desde, hasta) que hay que pedir al backend. */
export function rangeFor(view, anchor) {
  let first;
  let count;
  if (view === "dia") {
    first = startOfDay(anchor);
    count = 1;
  } else if (view === "semana") {
    first = startOfWeek(anchor);
    count = 7;
  } else {
    first = startOfWeek(new Date(anchor.getFullYear(), anchor.getMonth(), 1));
    count = 42;
  }
  const days = Array.from({ length: count }, (_, i) => addDays(first, i));
  return { days, desde: first, hasta: addDays(first, count) };
}

export function stepAnchor(view, anchor, direction) {
  if (view === "dia") return addDays(anchor, direction);
  if (view === "semana") return addDays(anchor, 7 * direction);
  return new Date(anchor.getFullYear(), anchor.getMonth() + direction, 1);
}

export function titleFor(view, anchor) {
  if (view === "mes") return anchor.toLocaleDateString("es-CL", { month: "long", year: "numeric" });
  if (view === "dia") return anchor.toLocaleDateString("es-CL", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const { days } = rangeFor("semana", anchor);
  const fmt = (d) => d.toLocaleDateString("es-CL", { day: "numeric", month: "short" });
  return `${fmt(days[0])} – ${fmt(days[6])} ${days[6].getFullYear()}`;
}

/** Eventos agrupados por dia local de inicio, en orden de hora. */
export function eventsByDay(events) {
  const groups = new Map();
  [...events]
    .sort((a, b) => parseUtc(a.inicio) - parseUtc(b.inicio))
    .forEach((event) => {
      const key = dayKey(parseUtc(event.inicio));
      groups.set(key, [...(groups.get(key) || []), event]);
    });
  return groups;
}

/** Nuevo inicio/fin (ISO UTC) al soltar el evento en otro dia: conserva la hora local y la duracion. */
export function moveToDay(event, targetDay) {
  const start = parseUtc(event.inicio);
  const duration = parseUtc(event.fin) - start;
  const moved = new Date(targetDay.getFullYear(), targetDay.getMonth(), targetDay.getDate(), start.getHours(), start.getMinutes());
  return { inicio: moved.toISOString(), fin: new Date(moved.getTime() + duration).toISOString() };
}

/** Valor para <input type="datetime-local"> (hora local). */
export const toLocalInput = (date) =>
  `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;

/** ISO UTC de un valor de <input type="datetime-local">. */
export const fromLocalInput = (value) => new Date(value).toISOString();

export const formatTime = (value) =>
  parseUtc(value)?.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" }) ?? "";

export const TIPO_LABEL = { presencial: "Presencial", virtual: "Virtual", llamada: "Llamada" };
export const ESTADO_LABEL = { planificada: "Planificada", realizada: "Realizada", cancelada: "Cancelada" };
