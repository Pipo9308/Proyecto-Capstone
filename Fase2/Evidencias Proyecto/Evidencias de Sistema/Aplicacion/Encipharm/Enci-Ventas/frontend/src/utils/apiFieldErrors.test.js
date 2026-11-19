import { describe, expect, it } from "vitest";
import { fieldErrorsFromApi } from "./apiFieldErrors";

const apiError = (body) => ({ details: { body } });

describe("fieldErrorsFromApi", () => {
  it("un 422 de validacion se reparte por campo", () => {
    const errors = fieldErrorsFromApi(apiError({
      detalles: [
        { loc: ["body", "rut"], msg: "Value error, El digito verificador del RUT no coincide", type: "value_error" },
        { loc: ["body", "rubro"], msg: "Field required", type: "missing" },
        { loc: ["body", "empresa"], msg: "String should have at least 1 character", type: "string_too_short" },
        { loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" },
      ],
    }));

    expect(errors).toEqual({
      rut: "El digito verificador del RUT no coincide",
      rubro: "Campo obligatorio.",
      empresa: "Campo obligatorio.",
      email: "Ingresa un correo valido.",
    });
  });

  it("un conflicto del servicio apunta al campo indicado con el mensaje del backend", () => {
    const errors = fieldErrorsFromApi(apiError({
      error: "Ya existe un cliente con ese RUT: Avicola Los Pinos (asignado a Vend 1)",
      codigo: "ERR_RUT_DUPLICADO",
      detalles: { campo: "rut", empresa: "Avicola Los Pinos" },
    }));

    expect(errors).toEqual({ rut: "Ya existe un cliente con ese RUT: Avicola Los Pinos (asignado a Vend 1)" });
  });

  it("sin detalles utiles devuelve un objeto vacio", () => {
    expect(fieldErrorsFromApi(apiError({ error: "Error" }))).toEqual({});
    expect(fieldErrorsFromApi(new Error("x"))).toEqual({});
    expect(fieldErrorsFromApi(null)).toEqual({});
  });

  it("conserva el primer error de cada campo", () => {
    const errors = fieldErrorsFromApi(apiError({
      detalles: [
        { loc: ["body", "rut"], msg: "primero" },
        { loc: ["body", "rut"], msg: "segundo" },
      ],
    }));

    expect(errors.rut).toBe("primero");
  });
});
