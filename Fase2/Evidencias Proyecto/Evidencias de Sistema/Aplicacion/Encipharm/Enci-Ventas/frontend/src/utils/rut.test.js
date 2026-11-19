import { describe, expect, it } from "vitest";
import { computeDv, formatRut, normalizeRut, rutError } from "./rut";

describe("RUT", () => {
  it("normaliza distintos formatos al canonico", () => {
    for (const raw of ["12.345.678-5", "12345678-5", "123456785", " 12 345 678 - 5 "]) {
      expect(normalizeRut(raw)).toBe("12345678-5");
    }
    expect(normalizeRut("11.111.111-1")).toBe("11111111-1");
  });

  it("calcula el digito verificador, incluido K y 0", () => {
    expect(computeDv("12345678")).toBe("5");
    const kBody = Array.from({ length: 1_000_000 }, (_, i) => String(1_000_000 + i)).find((b) => computeDv(b) === "K");
    expect(normalizeRut(`${kBody}-k`)).toBe(`${kBody}-K`);
    const zeroBody = Array.from({ length: 1_000_000 }, (_, i) => String(1_000_000 + i)).find((b) => computeDv(b) === "0");
    expect(normalizeRut(`${zeroBody}-0`)).toBe(`${zeroBody}-0`);
  });

  it("rechaza digito verificador incorrecto y formatos invalidos", () => {
    expect(normalizeRut("12.345.678-4")).toBeNull();
    expect(normalizeRut("abc")).toBeNull();
    expect(normalizeRut("123")).toBeNull();
    expect(normalizeRut("")).toBeNull();
  });

  it("da un mensaje claro para cada caso", () => {
    expect(rutError("")).toBe("Campo obligatorio.");
    expect(rutError("12")).toContain("RUT valido");
    expect(rutError("12.345.678-4")).toContain("verificador");
    expect(rutError("12.345.678-5")).toBe("");
  });

  it("formatRut muestra puntos y deja intacto lo que no es un RUT", () => {
    expect(formatRut("123456785")).toBe("12.345.678-5");
    expect(formatRut("xyz")).toBe("xyz");
    expect(formatRut(null)).toBe("");
  });
});
