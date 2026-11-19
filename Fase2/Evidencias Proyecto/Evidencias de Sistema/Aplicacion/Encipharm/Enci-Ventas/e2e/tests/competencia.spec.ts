import { expect, test } from "@playwright/test";
import { apiGet, apiToken, login, resetData, USERS } from "./helpers";

test.beforeAll(resetData);

test("la comparacion muestra el precio por unidad y la diferencia de Encipharm", async ({ page }) => {
  await login(page, USERS.supervisor);
  await page.goto("/competencia");

  await page.getByRole("combobox").filter({ hasText: "Enci-Ivermec 1%" }).first().selectOption({ label: "Enci-Ivermec 1%" });

  const fila = page.locator("tr", { hasText: "Ivomec" }).filter({ hasText: "Zoetis" }).first();
  await expect(fila).toContainText("$93 / ml");
  await expect(fila).toContainText("-18,28%");
});

test("un vendedor reporta un precio y queda pendiente; el supervisor lo aprueba y cambia la comparacion", async ({ browser }) => {
  // 1. Ana reporta
  const ana = await browser.newPage();
  await login(ana, USERS.ana);
  await ana.goto("/competencia");
  const form = ana.getByRole("form", { name: "Reportar precio" });
  await form.getByLabel("Producto de la competencia").selectOption({ label: "Zoetis · Ivomec (Frasco 500 ml)" });
  await form.getByLabel("Precio (CLP)").fill("52000");
  await form.getByLabel("Fuente").fill("Visita E2E");
  await form.getByRole("button", { name: "Reportar precio" }).click();
  await expect(ana.getByText(/pendiente de aprobación/)).toBeVisible();
  await ana.close();

  // sigue sin contar: la comparacion usa todavia el ultimo precio aprobado ($93 / ml)
  const tokenSup = await apiToken(USERS.supervisor);
  const antes = await apiGet<any>("/competencia/comparativa?productoEncipharmId=demo4-e1", tokenSup);
  expect(antes.equivalentes.find((e: any) => e.nombre === "Ivomec").precioPorUnidad).toBe(93);

  // 2. La supervisora aprueba
  const sup = await browser.newPage();
  await login(sup, USERS.supervisor);
  await sup.goto("/competencia");
  const fila = sup.locator("tr", { hasText: "Visita E2E" });
  await expect(fila).toBeVisible();
  await fila.getByRole("button", { name: "Aprobar" }).click();
  await expect(fila).toHaveCount(0);

  // 3. La comparacion ahora usa el precio nuevo: 52000 / 500 ml = $104 / ml; Encipharm (76) queda 26,92 % mas barato
  await sup.reload();
  await sup.getByRole("combobox").filter({ hasText: "Enci-Ivermec 1%" }).first().selectOption({ label: "Enci-Ivermec 1%" });
  const fila2 = sup.locator("tr", { hasText: "Ivomec" }).filter({ hasText: "Zoetis" }).first();
  await expect(fila2).toContainText("$104 / ml");
  await expect(fila2).toContainText("-26,92%");
  await sup.close();
});

test("un reporte descartado no cambia la comparacion", async ({ browser }) => {
  const sup = await browser.newPage();
  await login(sup, USERS.supervisor);
  await sup.goto("/competencia");
  const fila = sup.locator("tr", { hasText: "Lista de precios del distribuidor" }).first();
  await expect(fila).toBeVisible(); // reporte pendiente sembrado (Dectomax, de Beto)

  await fila.getByRole("button", { name: "Descartar" }).click();

  await expect(fila).toHaveCount(0);
  const token = await apiToken(USERS.supervisor);
  const descartados = await apiGet<any>("/competencia/precios?estado=descartado", token);
  expect(descartados.total).toBeGreaterThanOrEqual(2);
  await sup.close();
});

test("el supervisor agrega un producto al catalogo y lo ve en la comparacion", async ({ page }) => {
  await login(page, USERS.supervisor);
  await page.goto("/competencia");
  const form = page.getByRole("form", { name: "Agregar producto Encipharm" });

  await form.getByLabel("Nombre").fill("Enci-E2E 5%");
  await form.getByLabel("Cantidad por envase").fill("250");
  await form.getByLabel("Precio de lista (CLP)").fill("25000");
  await form.getByRole("button", { name: "Agregar" }).click();

  await expect(page.getByText("Producto Encipharm agregado.")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("option", { name: "Enci-E2E 5%" })).toBeAttached();
});
