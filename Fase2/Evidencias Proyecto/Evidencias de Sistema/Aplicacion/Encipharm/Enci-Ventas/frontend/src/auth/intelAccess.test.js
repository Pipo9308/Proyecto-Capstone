import { describe, expect, it } from "vitest";
import { visibleNavSections } from "../components/navigation";
import { hasIntelAccess } from "./roles";

const paths = (user) => visibleNavSections(user).flatMap((section) => section.items.map((item) => item.path));

describe("permiso Acceso a Inteligencia", () => {
  it("el admin siempre lo tiene", () => {
    expect(hasIntelAccess({ rol: "admin", accesoInteligencia: false })).toBe(true);
  });

  it("un vendedor solo lo tiene si se le concedio", () => {
    expect(hasIntelAccess({ rol: "vendedor", accesoInteligencia: true })).toBe(true);
    expect(hasIntelAccess({ rol: "vendedor", accesoInteligencia: false })).toBe(false);
    expect(hasIntelAccess({ rol: "vendedor" })).toBe(false);
    expect(hasIntelAccess(null)).toBe(false);
  });

  it("el menu oculta Inteligencia y Competencia sin el permiso", () => {
    const sinPermiso = paths({ rol: "vendedor", accesoInteligencia: false });
    expect(sinPermiso).not.toContain("/inteligencia");
    expect(sinPermiso).not.toContain("/competencia");
    expect(sinPermiso).toContain("/dashboard");
  });

  it("el menu muestra Inteligencia y Competencia con el permiso", () => {
    const conPermiso = paths({ rol: "vendedor", accesoInteligencia: true });
    expect(conPermiso).toContain("/inteligencia");
    expect(conPermiso).toContain("/competencia");
  });

  it("el menu enlaza las pantallas de gestion de clientes", () => {
    expect(paths({ rol: "vendedor" })).toEqual(expect.arrayContaining(["/clientes", "/crear", "/interacciones", "/propuestas"]));
  });
});
