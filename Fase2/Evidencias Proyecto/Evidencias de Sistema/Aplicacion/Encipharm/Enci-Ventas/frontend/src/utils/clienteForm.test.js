import { describe, expect, it } from "vitest";
import { clienteInitialForm, validateClienteForm } from "./clienteForm";

const valid = { ...clienteInitialForm, nombre: "Maria Soto", empresa: "Avicola Los Pinos", rut: "12.345.678-5", rubro: "Aves" };

describe("validateClienteForm", () => {
  it("acepta el minimo: contacto, empresa, RUT e industria", () => {
    const { isValid, payload } = validateClienteForm(valid);

    expect(isValid).toBe(true);
    expect(payload.rut).toBe("12345678-5");
    expect(payload.email).toBeNull();
    expect(payload.telefono).toBeNull();
    expect(payload.region).toBeNull();
  });

  it("exige exactamente los mismos campos que el backend", () => {
    const { errors } = validateClienteForm(clienteInitialForm);

    expect(Object.keys(errors).sort()).toEqual(["empresa", "nombre", "rubro", "rut"]);
    expect(errors.rut).toBe("Campo obligatorio.");
  });

  it("email, telefono y region son opcionales pero se validan si vienen", () => {
    expect(validateClienteForm({ ...valid, email: "no-es-correo" }).errors.email).toBe("Ingresa un correo valido.");
    expect(validateClienteForm({ ...valid, telefono: "1234" }).errors.telefono).toContain("8 digitos");
    expect(validateClienteForm({ ...valid, email: "A@B.cl", telefono: "+56 9 8765 4321", region: "Maule" }).isValid).toBe(true);
  });

  it("valida el digito verificador del RUT", () => {
    expect(validateClienteForm({ ...valid, rut: "12.345.678-4" }).errors.rut).toContain("verificador");
    expect(validateClienteForm({ ...valid, rut: "abc" }).errors.rut).toContain("RUT valido");
  });

  it("al editar un cliente anterior sin RUT, dejarlo vacio es valido", () => {
    const form = { ...valid, rut: "" };

    expect(validateClienteForm(form).errors.rut).toBe("Campo obligatorio.");
    const edited = validateClienteForm(form, { requireRut: false });
    expect(edited.isValid).toBe(true);
    expect(edited.payload.rut).toBeNull();
  });

  it("rechaza caracteres de formula y texto con simbolos raros", () => {
    expect(validateClienteForm({ ...valid, empresa: "=SUMA(1)" }).errors.empresa).toContain("formula");
    expect(validateClienteForm({ ...valid, rubro: "Aves <b>" }).errors.rubro).toContain("signos");
  });

  it("solo envia vendedorUid cuando se eligio uno", () => {
    expect(validateClienteForm(valid).payload).not.toHaveProperty("vendedorUid");
    expect(validateClienteForm({ ...valid, vendedorUid: "u-7" }).payload.vendedorUid).toBe("u-7");
  });
});
