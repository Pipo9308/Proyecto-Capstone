import { describe, expect, it } from "vitest";
import { addDays, dayKey, eventsByDay, fromLocalInput, moveToDay, rangeFor, startOfWeek, stepAnchor, toLocalInput } from "./calendario";

// 2026-10-14 es miercoles.
const wed = new Date(2026, 9, 14, 10, 30);

describe("calendario", () => {
  it("la semana empieza el lunes", () => {
    expect(dayKey(startOfWeek(wed))).toBe("2026-10-12");
    expect(dayKey(startOfWeek(new Date(2026, 9, 18)))).toBe("2026-10-12"); // domingo
    expect(dayKey(startOfWeek(new Date(2026, 9, 12)))).toBe("2026-10-12");
  });

  it("el mes se muestra en 6 semanas completas y pide ese rango al backend", () => {
    const { days, desde, hasta } = rangeFor("mes", wed);

    expect(days).toHaveLength(42);
    expect(dayKey(days[0])).toBe("2026-09-28"); // lunes anterior al 1 de octubre
    expect(dayKey(days[41])).toBe("2026-11-08");
    expect(dayKey(desde)).toBe("2026-09-28");
    expect(dayKey(hasta)).toBe("2026-11-09");
  });

  it("semana y dia", () => {
    expect(rangeFor("semana", wed).days.map(dayKey)[0]).toBe("2026-10-12");
    expect(rangeFor("semana", wed).days).toHaveLength(7);
    expect(rangeFor("dia", wed).days.map(dayKey)).toEqual(["2026-10-14"]);
  });

  it("avanzar y retroceder respeta cada vista", () => {
    expect(dayKey(stepAnchor("dia", wed, 1))).toBe("2026-10-15");
    expect(dayKey(stepAnchor("semana", wed, -1))).toBe("2026-10-07");
    expect(dayKey(stepAnchor("mes", wed, 1))).toBe("2026-11-01");
    expect(dayKey(stepAnchor("mes", new Date(2026, 0, 31), -1))).toBe("2025-12-01");
  });

  it("agrupa por dia local en orden de hora", () => {
    const at = (d, h) => new Date(2026, 9, d, h).toISOString();
    const grouped = eventsByDay([
      { id: "tarde", inicio: at(14, 16), fin: at(14, 17) },
      { id: "otro-dia", inicio: at(15, 9), fin: at(15, 10) },
      { id: "manana", inicio: at(14, 9), fin: at(14, 10) },
    ]);

    expect(grouped.get("2026-10-14").map((e) => e.id)).toEqual(["manana", "tarde"]);
    expect(grouped.get("2026-10-15").map((e) => e.id)).toEqual(["otro-dia"]);
  });

  it("mover a otro dia conserva la hora local y la duracion", () => {
    const event = { inicio: new Date(2026, 9, 14, 10, 30).toISOString(), fin: new Date(2026, 9, 14, 12, 0).toISOString() };

    const moved = moveToDay(event, new Date(2026, 9, 21));

    expect(new Date(moved.inicio)).toEqual(new Date(2026, 9, 21, 10, 30));
    expect(new Date(moved.fin)).toEqual(new Date(2026, 9, 21, 12, 0));
  });

  it("los valores de datetime-local viajan de ida y vuelta", () => {
    const local = toLocalInput(new Date(2026, 9, 14, 9, 5));

    expect(local).toBe("2026-10-14T09:05");
    expect(new Date(fromLocalInput(local))).toEqual(new Date(2026, 9, 14, 9, 5));
  });

  it("addDays cruza fin de mes", () => {
    expect(dayKey(addDays(new Date(2026, 9, 31), 1))).toBe("2026-11-01");
  });
});
