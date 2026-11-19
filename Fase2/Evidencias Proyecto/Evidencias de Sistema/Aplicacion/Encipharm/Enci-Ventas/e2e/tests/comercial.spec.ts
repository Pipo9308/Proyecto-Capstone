import { expect, test } from "@playwright/test";
import { apiGet, apiToken, login, resetData, USERS } from "./helpers";

test.beforeAll(resetData);

test("flujo comercial completo: oportunidad, propuesta, aprobacion y aviso al vendedor", async ({ browser }) => {
  // 1. Ana crea una oportunidad para su cliente
  const ana = await browser.newPage();
  await login(ana, USERS.ana);
  await ana.goto("/oportunidades");
  await ana.getByRole("button", { name: "Nueva oportunidad" }).click();
  const modal = ana.locator("form").filter({ has: ana.getByRole("heading", { name: "Nueva oportunidad" }) });
  await expect(modal.getByRole("option", { name: "Avícola Los Pinos" })).toBeAttached();
  await modal.getByLabel("Cliente").selectOption({ label: "Avícola Los Pinos" });
  await modal.locator('input[name="titulo"]').fill("Programa E2E 2026");
  await modal.locator('input[name="valorEstimado"]').fill("5000000");
  await modal.locator('input[name="probabilidad"]').fill("60");
  await modal.getByRole("button", { name: "Guardar oportunidad" }).click();
  await expect(ana.getByRole("button", { name: "Avícola Los Pinos" }).first()).toBeVisible();

  // 2. y una propuesta sobre esa oportunidad, con 10 % de descuento
  await ana.goto("/propuestas");
  const form = ana.locator("form.form-card");
  const clienteSelect = form.locator('select[name="clienteId"]');
  await expect(clienteSelect.getByRole("option", { name: "Avícola Los Pinos" })).toBeAttached();
  await clienteSelect.selectOption({ label: "Avícola Los Pinos" });
  await form.locator('select[name="oportunidadId"]').selectOption({ label: "Programa E2E 2026" });
  await form.locator('input[name="titulo"]').fill("Oferta E2E");
  await form.locator('input[name="montoNeto"]').fill("1000000");
  await form.locator('input[name="descuentoPct"]').fill("10");
  await form.getByRole("button", { name: "Crear propuesta" }).click();
  const tarjeta = ana.locator(".propuesta-card", { hasText: "Oferta E2E" });
  await expect(tarjeta).toBeVisible();
  await expect(tarjeta).toContainText("borrador");
  await expect(tarjeta).toContainText(/Total: \$900[.,]000/); // 1.000.000 - 10 %
  await ana.close();

  // 3. La supervisora la aprueba
  const sup = await browser.newPage();
  await login(sup, USERS.supervisor);
  await sup.goto("/propuestas");
  const tarjetaSup = sup.locator(".propuesta-card", { hasText: "Oferta E2E" });
  await tarjetaSup.locator("select").selectOption("aceptada");
  await expect(tarjetaSup).toContainText("aceptada");
  await sup.close();

  // 4. A Ana le llega el aviso con el nuevo estado
  const token = await apiToken(USERS.ana);
  const avisos = await apiGet<{ items: { titulo: string; enlace: string }[] }>("/notificaciones", token);
  const aviso = avisos.items.find((n) => n.titulo.includes("Oferta E2E"));
  expect(aviso?.titulo).toContain("aceptada");
  expect(aviso?.enlace).toBe("/propuestas");
});

test("un vendedor no puede ver ni tocar las propuestas de otro", async ({ page }) => {
  await login(page, USERS.beto);
  await page.goto("/propuestas");

  await expect(page.locator(".propuesta-card", { hasText: "Oferta E2E" })).toHaveCount(0);
});

test("el dashboard del vendedor carga con sus numeros", async ({ page }) => {
  await login(page, USERS.ana);

  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByText(/Proyeccion Ponderada/i).first()).toBeVisible();
});
