import { expect, test } from "@playwright/test";
import { login, resetData, USERS } from "./helpers";

test.beforeAll(resetData);

// Estas pruebas dependen de que Enci-Intel (puerto 8080) este arriba; sus alertas pueden estar vacias en local.

test("la pantalla de Inteligencia carga alertas o dice que no hay, sin romperse", async ({ page }) => {
  await login(page, USERS.ana);
  await page.goto("/inteligencia");

  await expect(page.getByText("Alertas de la competencia")).toBeVisible();
  const feed = page.locator(".static-news-feed");
  await expect(feed.getByText(/Cargando alertas/)).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Todas" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Regulación" })).toBeVisible();
});

test("el chat de competencia responde con un error claro si no hay modelo configurado", async ({ page }) => {
  await login(page, USERS.ana);
  await page.goto("/inteligencia");

  await page.getByLabel("Pregunta").fill("¿Qué productos nuevos registró la competencia?");
  await page.getByRole("button", { name: "Enviar" }).click();

  // Sin DEEPSEEK_API_KEY el servidor avisa; lo importante es que la pantalla lo muestre y no se quede cargando.
  await expect(page.getByText("Pensando...")).toHaveCount(0, { timeout: 30_000 });
  await expect(page.getByRole("alert").or(page.locator(".static-ai-message").last())).toBeVisible();
});

test("una pregunta de ejemplo se puede enviar con un clic", async ({ page }) => {
  await login(page, USERS.ana);
  await page.goto("/inteligencia");

  await page.getByRole("button", { name: /precios conocemos/ }).click();

  await expect(page.getByText("Pensando...")).toHaveCount(0, { timeout: 30_000 });
  await expect(page.locator(".user-message-row").first()).toContainText("precios");
});
