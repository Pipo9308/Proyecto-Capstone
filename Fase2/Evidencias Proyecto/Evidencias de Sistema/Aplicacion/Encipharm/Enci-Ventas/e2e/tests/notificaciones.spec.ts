import { expect, test } from "@playwright/test";
import { apiGet, apiToken, login, resetData, USERS } from "./helpers";

test.beforeAll(async () => {
  await resetData();
  // Las visitas proximas se convierten en avisos cuando alguien consulta sus notificaciones (sin planificador), y esa
  // revision tiene un tope de una por minuto en el servidor: se consulta hasta que aparezcan.
  test.setTimeout(150_000);
  const token = await apiToken(USERS.ana);
  for (let i = 0; i < 24; i++) {
    const page = await apiGet<{ noLeidas: number }>("/notificaciones", token);
    if (page.noLeidas >= 2) return;
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
});

const unread = async (page: import("@playwright/test").Page) =>
  Number(((await page.getByRole("button", { name: /Notificaciones/ }).getAttribute("aria-label")) ?? "").match(/\((\d+)/)?.[1] ?? "0");

test("la campana muestra cuantos avisos sin leer tiene el usuario", async ({ page }) => {
  await login(page, USERS.ana);

  await expect(page.getByRole("button", { name: /Notificaciones \(\d+ sin leer\)/ })).toBeVisible();
});

test("abrir un aviso lo marca como leido y lleva a su pantalla", async ({ page }) => {
  await login(page, USERS.ana);
  await expect(page.getByRole("button", { name: /Notificaciones \(\d+ sin leer\)/ })).toBeVisible();
  const antes = await unread(page);
  expect(antes).toBeGreaterThanOrEqual(2);

  await page.getByRole("button", { name: /Notificaciones/ }).click();
  const panel = page.getByRole("dialog", { name: "Notificaciones" });
  await expect(panel.getByText(/Visita en menos de 1 hora/)).toBeVisible();
  await panel.getByText(/Visita en menos de 1 hora/).click();

  await expect(page).toHaveURL(/\/calendario/);
  expect(await unread(page)).toBe(antes - 1);
});

test("marcar todas como leidas deja el contador en cero", async ({ page }) => {
  await login(page, USERS.ana);

  await page.getByRole("button", { name: /Notificaciones/ }).click();
  await page.getByRole("button", { name: "Marcar todas como leídas" }).click();

  await expect(page.getByRole("button", { name: "Notificaciones", exact: true })).toBeVisible();
});

test("cada usuario solo ve sus propios avisos", async ({ page }) => {
  await login(page, USERS.beto);

  await page.getByRole("button", { name: /Notificaciones/ }).click();
  const panel = page.getByRole("dialog", { name: "Notificaciones" });

  await expect(panel.getByText(/Lechería Santa Clara/)).toHaveCount(0); // es el aviso de Ana
});
