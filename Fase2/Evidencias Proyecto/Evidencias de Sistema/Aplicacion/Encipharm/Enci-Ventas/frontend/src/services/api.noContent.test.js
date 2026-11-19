import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch, deleteCliente } from "./api";

describe("respuestas 204 No Content", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("deleteCliente no falla cuando el backend responde 204 sin cuerpo", async () => {
    const json = vi.fn().mockRejectedValue(new SyntaxError("Unexpected end of JSON input"));
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, status: 204, json });

    await expect(deleteCliente("jwt-token", "cliente-1")).resolves.toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });

  it("un 204 de una mutacion avisa que los datos cambiaron", async () => {
    const mutated = vi.fn();
    window.addEventListener("enci:data-mutated", mutated);
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true, status: 204, json: vi.fn() });

    const result = await apiFetch("/clientes/cliente-1", { method: "DELETE", token: "jwt-token" });

    window.removeEventListener("enci:data-mutated", mutated);
    expect(result).toBeNull();
    expect(mutated).toHaveBeenCalledTimes(1);
  });

  it("una respuesta 200 con cuerpo no JSON sigue siendo un error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => null },
      json: vi.fn().mockRejectedValue(new SyntaxError("bad json")),
    });

    await expect(apiFetch("/clientes", { token: "jwt-token" })).rejects.toMatchObject({ status: 200 });
  });
});
