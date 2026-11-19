import { describe, expect, it } from "vitest";
import { buildAlertFilters, filterAlerts, parseUtc, priorityLabel, REGULACION } from "./alertas";
import { diffClass, formatDiff, perUnit } from "./competencia";

const alerts = [
  { id: "1", competitor: "Zoetis", type: "LAUNCH" },
  { id: "2", competitor: "Agrovet", type: "REGULATORY" },
  { id: "3", competitor: "Zoetis", type: "REGULATORY" },
  { id: "4", competitor: null, type: "LAUNCH" },
];

describe("alertas", () => {
  it("las fechas sin zona se leen como UTC", () => {
    expect(parseUtc("2026-10-01T10:00:00").toISOString()).toBe("2026-10-01T10:00:00.000Z");
    expect(parseUtc("2026-10-01T10:00:00-03:00").toISOString()).toBe("2026-10-01T13:00:00.000Z");
    expect(parseUtc("no es fecha")).toBeNull();
    expect(parseUtc(null)).toBeNull();
  });

  it("los filtros salen de los competidores reales y siempre incluyen Todas y Regulación", () => {
    expect(buildAlertFilters(alerts)).toEqual(["Todas", "Agrovet", "Zoetis", REGULACION]);
    expect(buildAlertFilters([])).toEqual(["Todas", REGULACION]);
  });

  it("filtra por competidor o por regulación", () => {
    expect(filterAlerts(alerts, "Todas")).toHaveLength(4);
    expect(filterAlerts(alerts, "Zoetis").map((a) => a.id)).toEqual(["1", "3"]);
    expect(filterAlerts(alerts, REGULACION).map((a) => a.id)).toEqual(["2", "3"]);
  });

  it("etiqueta la prioridad y cae en Baja si no la conoce", () => {
    expect(priorityLabel("CRITICAL")).toBe("Crítica");
    expect(priorityLabel("x")).toBe("Baja");
  });
});

describe("competencia", () => {
  it("formatea diferencias con signo y sin dato", () => {
    expect(formatDiff(-20)).toBe("-20%");
    expect(formatDiff(12.5)).toBe("+12,5%");
    expect(formatDiff(null)).toBe("—");
  });

  it("negativo es mejor para Encipharm", () => {
    expect([diffClass(-5), diffClass(5), diffClass(0), diffClass(null)]).toEqual(["mejor", "peor", "similar", "similar"]);
  });

  it("precio por unidad", () => {
    expect(perUnit(100, "ml")).toBe("$100 / ml");
    expect(perUnit(null, "ml")).toBe("—");
  });
});
