import { expect, test } from "@playwright/test";
import { login, resetData, USERS } from "./helpers";

test.beforeAll(resetData);

const nav = (page: import("@playwright/test").Page, name: string | RegExp) =>
  page.locator(".sidebar-nav").getByRole("link", { name });

test("el supervisor ve Equipo de Ventas e Inteligencia", async ({ page }) => {
  await login(page, USERS.supervisor);

  await expect(nav(page, "Equipo de Ventas")).toBeVisible();
  await expect(nav(page, "Inteligencia de Mercado")).toBeVisible();
  await expect(nav(page, /Competencia/)).toBeVisible();
  await expect(nav(page, "Calendario")).toBeVisible();
});

test("un vendedor con permiso de Inteligencia ve esas secciones pero no Equipo de Ventas", async ({ page }) => {
  await login(page, USERS.ana);

  await expect(nav(page, "Inteligencia de Mercado")).toBeVisible();
  await expect(nav(page, "Equipo de Ventas")).toHaveCount(0);
});

test("un vendedor sin permiso no ve Inteligencia ni Competencia en el menu", async ({ page }) => {
  await login(page, USERS.beto);

  await expect(nav(page, "Clientes")).toBeVisible();
  await expect(nav(page, "Inteligencia de Mercado")).toHaveCount(0);
  await expect(nav(page, /Competencia/)).toHaveCount(0);
});

test("escribir a mano la direccion de una seccion sin permiso no la abre", async ({ page }) => {
  await login(page, USERS.beto);

  await page.goto("/competencia");

  await expect(page.getByText("Reportar un precio")).toHaveCount(0);
  await expect(page.getByText("Comparación de precios")).toHaveCount(0);
});

test("un vendedor no entra a Equipo de Ventas escribiendo la direccion", async ({ page }) => {
  await login(page, USERS.ana);

  await page.goto("/equipo");

  await expect(page.getByRole("heading", { name: "Acceso restringido" })).toBeVisible();
});
