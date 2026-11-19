import assert from "node:assert/strict";
import { test } from "node:test";
import { toUiRole } from "./role.ts";

test("el rol admin del backend se muestra como administrador", () => {
  assert.equal(toUiRole("admin"), "administrador");
  assert.equal(toUiRole("Admin"), "administrador");
  assert.equal(toUiRole("administrador"), "administrador");
});

test("gerencia y comercial se conservan en minuscula", () => {
  assert.equal(toUiRole("Gerencia"), "gerencia");
  assert.equal(toUiRole("comercial"), "comercial");
});

test("un rol desconocido o ausente cae a pendiente", () => {
  assert.equal(toUiRole("root"), "pendiente");
  assert.equal(toUiRole(undefined), "pendiente");
  assert.equal(toUiRole(""), "pendiente");
});
