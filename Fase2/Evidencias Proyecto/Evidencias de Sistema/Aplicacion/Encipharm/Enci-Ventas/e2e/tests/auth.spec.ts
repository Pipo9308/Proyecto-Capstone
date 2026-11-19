import { expect, test } from "@playwright/test";
import { login, resetData, USERS } from "./helpers";

test.beforeAll(resetData);

test("entrar con credenciales validas lleva al panel", async ({ page }) => {
  await login(page, USERS.admin);

  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByText("Enci Sales Command").or(page.getByRole("heading").first())).toBeVisible();
});

test("una contraseña incorrecta no deja entrar y avisa", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("Correo electrónico").fill(USERS.admin.email);
  await page.getByPlaceholder("Contraseña").fill("incorrecta-123");
  await page.getByRole("button", { name: "Login" }).click();

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText(/incorrectos|no se pudo|invalid/i).first()).toBeVisible();
});

test("sin sesion, una pantalla protegida redirige al login", async ({ page }) => {
  await page.goto("/clientes");

  await expect(page).toHaveURL(/\/login/);
});

test("salir cierra la sesion y vuelve a pedir el login", async ({ page }) => {
  await login(page, USERS.ana);
  await page.getByRole("button", { name: "Salir" }).click();
  await page.goto("/clientes");

  await expect(page).toHaveURL(/\/login/);
});
