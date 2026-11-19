import { describe, expect, it } from "vitest";
import { passwordPolicyError } from "./passwordPolicy";

describe("passwordPolicyError", () => {
  it("acepta 10 o mas caracteres con letras y numeros", () => {
    expect(passwordPolicyError("ClaveSegura2026")).toBe("");
    expect(passwordPolicyError("abcdefghi1")).toBe("");
  });

  it("rechaza las demasiado cortas", () => {
    expect(passwordPolicyError("Corta1")).toContain("al menos 10");
    expect(passwordPolicyError("")).toContain("al menos 10");
  });

  it("exige letras y numeros", () => {
    expect(passwordPolicyError("soloLetrasAqui")).toContain("letras y numeros");
    expect(passwordPolicyError("1234567890123")).toContain("letras y numeros");
  });

  it("rechaza las que bcrypt no soporta (mas de 72 bytes)", () => {
    expect(passwordPolicyError("a1".repeat(40))).toContain("larga");
  });

  it("cuenta bytes, no caracteres: los acentos ocupan mas", () => {
    // 25 x ("ñ" = 2 bytes + "1" = 1 byte) = 75 bytes: son solo 50 caracteres pero pasan el limite de bcrypt.
    expect(passwordPolicyError("ñ1".repeat(25))).toContain("larga");
    expect(passwordPolicyError("ñ1".repeat(20))).toBe("");
  });
});
