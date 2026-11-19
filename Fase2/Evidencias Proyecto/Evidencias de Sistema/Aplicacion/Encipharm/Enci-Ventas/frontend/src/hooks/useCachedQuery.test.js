import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { clearApiGetCache } from "../services/api";
import useCachedQuery, { clearAllCachedQueries } from "./useCachedQuery";

const OPTIONS = { refreshMs: 0, refreshOnFocus: false };

describe("cache de queries al cerrar sesion", () => {
  beforeEach(() => {
    clearAllCachedQueries();
    sessionStorage.clear();
  });

  it("clearAllCachedQueries borra las claves de query y respeta las ajenas", () => {
    sessionStorage.setItem("enci-query:clientes:list:A", JSON.stringify([1]));
    sessionStorage.setItem("enci-query:dashboard:B:vendedor", JSON.stringify({ x: 1 }));
    sessionStorage.setItem("otra-cosa", "se-queda");

    clearAllCachedQueries();

    expect(sessionStorage.getItem("enci-query:clientes:list:A")).toBeNull();
    expect(sessionStorage.getItem("enci-query:dashboard:B:vendedor")).toBeNull();
    expect(sessionStorage.getItem("otra-cosa")).toBe("se-queda");
  });

  it("el siguiente usuario no ve los datos cacheados del anterior tras el logout", async () => {
    const fetcher = vi.fn().mockResolvedValue({ secreto: "datos-del-usuario-A" });

    const userA = renderHook(() => useCachedQuery("clientes:list", fetcher, OPTIONS));
    await waitFor(() => expect(userA.result.current.data).toEqual({ secreto: "datos-del-usuario-A" }));
    expect(sessionStorage.getItem("enci-query:clientes:list")).not.toBeNull();
    userA.unmount();

    // AuthProvider.logout() llama a clearApiGetCache(): antes era un no-op.
    clearApiGetCache();

    expect(sessionStorage.getItem("enci-query:clientes:list")).toBeNull();
    const userB = renderHook(() => useCachedQuery("clientes:list", fetcher, OPTIONS));
    expect(userB.result.current.data).toBeUndefined();
    expect(userB.result.current.loading).toBe(true);
  });

  it("sin logout, el cache si se reutiliza (el fix no lo desactiva)", async () => {
    const fetcher = vi.fn().mockResolvedValue(["cliente"]);

    const first = renderHook(() => useCachedQuery("clientes:list", fetcher, OPTIONS));
    await waitFor(() => expect(first.result.current.data).toEqual(["cliente"]));
    first.unmount();

    const second = renderHook(() => useCachedQuery("clientes:list", fetcher, OPTIONS));
    expect(second.result.current.data).toEqual(["cliente"]);
    expect(second.result.current.loading).toBe(false);
  });
});
