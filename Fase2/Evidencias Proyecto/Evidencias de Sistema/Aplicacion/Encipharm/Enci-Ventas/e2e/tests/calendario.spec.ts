import { expect, test, type Page } from "@playwright/test";
import { apiGet, apiToken, login, resetData, USERS } from "./helpers";

test.beforeAll(resetData);

const pad = (n: number) => String(n).padStart(2, "0");
/** "YYYY-MM-DDTHH:mm" (hora local) para un input datetime-local, `days` dias desde hoy. */
function localInput(days: number, hour: number, minute = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(hour)}:${pad(minute)}`;
}

async function abrirFormulario(page: Page) {
  await page.goto("/calendario");
  await page.getByRole("button", { name: "Nuevo evento" }).click();
  const dialog = page.getByRole("dialog", { name: "Nuevo evento" });
  await expect(dialog.getByRole("option", { name: "Avícola Los Pinos" })).toBeAttached();
  await dialog.getByRole("combobox", { name: "Cliente" }).selectOption({ label: "Avícola Los Pinos" });
  return dialog;
}

test("un vendedor agenda una visita y la ve en el calendario", async ({ page }) => {
  await login(page, USERS.ana);
  const dialog = await abrirFormulario(page);

  await dialog.getByLabel("Inicio").fill(localInput(0, 15));
  await dialog.getByLabel("Fin").fill(localInput(0, 16));
  await dialog.getByLabel("Lugar").fill("Plantel E2E");
  await dialog.getByRole("button", { name: "Guardar" }).click();

  await expect(page.getByText("Evento guardado.")).toBeVisible();
  await expect(page.locator(".cal-chip", { hasText: "Avícola Los Pinos" }).first()).toBeVisible();
});

test("al mover el inicio, el fin acompaña y se conserva la duracion", async ({ page }) => {
  await login(page, USERS.ana);
  const dialog = await abrirFormulario(page);
  await dialog.getByLabel("Inicio").fill(localInput(1, 9));
  await dialog.getByLabel("Fin").fill(localInput(1, 10, 30));

  await dialog.getByLabel("Inicio").fill(localInput(2, 14));

  await expect(dialog.getByLabel("Fin")).toHaveValue(localInput(2, 15, 30));
});

test("un evento de mas de 12 horas se explica antes de enviar", async ({ page }) => {
  await login(page, USERS.ana);
  const dialog = await abrirFormulario(page);
  await dialog.getByLabel("Inicio").fill(localInput(1, 8));
  await dialog.getByLabel("Fin").fill(localInput(2, 11));

  await dialog.getByRole("button", { name: "Guardar" }).click();

  await expect(dialog.getByRole("alert")).toContainText("no puede durar más de 12 horas");
});

test("marcar una visita como realizada la deja en el historial del cliente", async ({ page }) => {
  await login(page, USERS.ana);
  const dialog = await abrirFormulario(page);
  await dialog.getByLabel("Inicio").fill(localInput(0, 11));
  await dialog.getByLabel("Fin").fill(localInput(0, 12));
  await dialog.getByLabel("Lugar").fill("Visita para historial E2E");
  await dialog.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("Evento guardado.")).toBeVisible();

  await page.locator(".cal-chip").filter({ hasText: "11:00" }).first().click();
  await page.getByRole("button", { name: "Marcar como realizada" }).click();

  await expect(page.getByText(/historial del cliente/)).toBeVisible();
  const token = await apiToken(USERS.ana);
  const interacciones = await apiGet<any[]>("/interacciones?clienteId=demo4-c1", token);
  expect(interacciones.some((i) => i.resumen.includes("Visita para historial E2E"))).toBeTruthy();
});

test("arrastrar un evento a otro dia lo mueve conservando la hora", async ({ page }) => {
  await login(page, USERS.ana);
  const dialog = await abrirFormulario(page);
  // el dia 10 del mes siempre esta en la grilla del mes actual
  const now = new Date();
  const mes = `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
  await dialog.getByLabel("Inicio").fill(`${mes}-10T09:00`);
  await dialog.getByLabel("Fin").fill(`${mes}-10T10:00`);
  await dialog.getByLabel("Lugar").fill("Mover E2E");
  await dialog.getByRole("button", { name: "Guardar" }).click();
  await expect(page.getByText("Evento guardado.")).toBeVisible();

  const chip = page.locator(".cal-chip").filter({ hasText: "09:00" }).first();
  const destino = page.locator(".cal-day").filter({ has: page.getByRole("button", { name: "20", exact: true }) }).first();
  await chip.dragTo(destino);

  await expect(page.getByText("Evento movido.")).toBeVisible();
  const token = await apiToken(USERS.ana);
  const desde = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
  const hasta = new Date(now.getFullYear(), now.getMonth() + 1, 1).toISOString();
  const eventos = await apiGet<any[]>(`/eventos?desde=${desde}&hasta=${hasta}`, token);
  const movido = eventos.find((e) => e.lugar === "Mover E2E");
  const inicio = new Date(movido.inicio + "Z");
  expect(inicio.getDate()).toBe(20);
  expect(inicio.getHours()).toBe(9); // misma hora local
});

test("el supervisor ve los eventos de todo el equipo y puede filtrar por vendedor", async ({ page }) => {
  await login(page, USERS.supervisor);
  await page.goto("/calendario");

  const filtro = page.getByLabel("Filtrar por vendedor");
  await expect(filtro).toBeVisible();
  await filtro.selectOption({ label: "Beto Contreras" });

  await expect(page.locator(".cal-chip").filter({ hasText: "Avícola Los Pinos" })).toHaveCount(0); // son de Ana
});
