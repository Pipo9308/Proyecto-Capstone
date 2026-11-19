import { describe, expect, it } from "vitest";
import { formatFileSize, validatePdfFile } from "./archivos";

const file = (name, size) => ({ name, size });

describe("archivos", () => {
  it("formatea tamanos", () => {
    expect(formatFileSize(500)).toBe("500 B");
    expect(formatFileSize(2048)).toBe("2 KB");
    expect(formatFileSize(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(formatFileSize(undefined)).toBe("0 B");
  });

  it("acepta un PDF dentro del limite", () => {
    expect(validatePdfFile(file("oferta.pdf", 1000))).toBe("");
    expect(validatePdfFile(file("OFERTA.PDF", 20 * 1024 * 1024))).toBe("");
  });

  it("rechaza lo que no es PDF, lo vacio y lo que pasa los 20 MB", () => {
    expect(validatePdfFile(file("hoja.xlsx", 1000))).toContain("PDF");
    expect(validatePdfFile(file("oferta.pdf", 0))).toContain("vacio");
    expect(validatePdfFile(file("oferta.pdf", 20 * 1024 * 1024 + 1))).toContain("20 MB");
    expect(validatePdfFile(null)).toContain("Selecciona");
  });
});
