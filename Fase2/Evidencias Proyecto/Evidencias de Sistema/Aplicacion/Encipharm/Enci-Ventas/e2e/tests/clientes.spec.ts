import { expect, test } from "@playwright/test";
import { API, apiGet, apiToken, login, resetData, rutValido, USERS } from "./helpers";

const RUT = rutValido(15222333);

// Cada prueba parte de lo mismo: un cliente de Ana ya creado (por la API, para no depender del orden de las pruebas).
test.beforeAll(async () => {
  await resetData();
  const token = await apiToken(USERS.ana);
  const res = await fetch(`${API}/clientes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ nombre: "Contacto E2E", empresa: "Avicola E2E Uno", rut: RUT, rubro: "Avicola" }),
  });
  if (!res.ok) throw new Error(`No se pudo preparar el cliente: ${res.status}`);
});

async function crearCliente(page: import("@playwright/test").Page, data: { empresa: string; rut: string; nombre?: string }) {
  await page.goto("/crear");
  await page.getByPlaceholder("Nombre del contacto").fill(data.nombre ?? "Contacto E2E");
  await page.getByPlaceholder("Empresa o razon social").fill(data.empresa);
  await page.getByPlaceholder("12.345.678-5").fill(data.rut);
  await page.getByPlaceholder("Aves, Cerdos, Rumiantes...").fill("Avicola");
  await page.getByRole("button", { name: "Guardar Cliente" }).click();
}

test("un vendedor crea un cliente y aparece primero en la lista", async ({ page }) => {
  await login(page, USERS.ana);

  await crearCliente(page, { empresa: "Avicola E2E Dos", rut: rutValido(16333444) });
  await expect(page.getByRole("status")).toBeVisible(); // modal de exito
  await page.goto("/clientes");

  await expect(page.locator(".client-card").first()).toContainText("Avicola E2E Dos");
});

test("el administrador ve el cliente que creo el vendedor, arriba de la lista", async ({ page }) => {
  // el vendedor crea uno nuevo (por la API) y el admin, en otra sesion, lo debe ver primero
  const tokenAna = await apiToken(USERS.ana);
  const res = await fetch(`${API}/clientes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${tokenAna}` },
    body: JSON.stringify({ nombre: "Reciente", empresa: "Cliente Mas Reciente SA", rut: rutValido(17444555), rubro: "Aves" }),
  });
  expect(res.ok).toBeTruthy();
  await login(page, USERS.admin);

  await page.goto("/clientes");

  await expect(page.locator(".client-card").first()).toContainText("Cliente Mas Reciente SA");
  const all = await apiGet<any[]>("/clientes?limit=500", await apiToken(USERS.admin));
  expect(all.find((c) => c.empresa === "Cliente Mas Reciente SA")?.vendedorUid).toBe("demo4-ana");
});

test("un RUT repetido se rechaza e indica cual cliente lo tiene", async ({ page }) => {
  await login(page, USERS.ana);

  await crearCliente(page, { empresa: "Duplicado SA", rut: RUT });

  await expect(page.getByText(/Ya existe un cliente con ese RUT/)).toBeVisible();
  await expect(page.getByText(/Avicola E2E Uno/).first()).toBeVisible();
});

test("un RUT con digito verificador malo se rechaza", async ({ page }) => {
  await login(page, USERS.ana);

  await crearCliente(page, { empresa: "RUT Malo SA", rut: "15222333-0" });

  await expect(page.getByText(/rut/i).filter({ hasText: /invalid|valido|verificador|incorrect/i }).first()).toBeVisible();
});

test("la busqueda filtra la lista por nombre de empresa", async ({ page }) => {
  await login(page, USERS.admin);
  await page.goto("/clientes");

  await page.getByPlaceholder(/Buscar por cliente/).fill("E2E Uno");

  await expect(page.locator(".client-card")).toHaveCount(1);
});

test("un vendedor solo ve sus propios clientes", async ({ page }) => {
  await login(page, USERS.beto);
  await page.goto("/clientes");

  await expect(page.locator(".client-card").first()).toBeVisible();
  await expect(page.getByText("Avicola E2E Uno")).toHaveCount(0); // es de Ana
});
