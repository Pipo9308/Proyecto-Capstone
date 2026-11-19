import { execSync } from "node:child_process";
import { expect, type Page } from "@playwright/test";

export const API = process.env.E2E_API_URL ?? "http://localhost:8000";
// Emulador de Firestore del compose de Ventas (puerto 8086 del equipo) y su id de proyecto.
const EMULATOR = process.env.E2E_FIRESTORE_URL ?? "http://localhost:8086";
const PROJECT = process.env.E2E_FIREBASE_PROJECT ?? "enci-local";
const DOCKER_BIN = process.env.DOCKER_BIN ?? "C:\Users\sanch\AppData\Local\Programs\DockerDesktop\resources\bin";

export const USERS = {
  admin: { email: "admin@enci.cl", password: "admin123" },
  supervisor: { email: "sofia.supervisora@enci.cl", password: "Demo12345678" },
  ana: { email: "ana.vendedora@enci.cl", password: "Demo12345678" }, // vendedora con acceso a Inteligencia
  beto: { email: "beto.vendedor@enci.cl", password: "Demo12345678" }, // vendedor SIN acceso a Inteligencia
};

/** Vacia el emulador y vuelve a sembrar el admin y los datos de demostracion. Tarda ~15 s. */
export async function resetData(): Promise<void> {
  const res = await fetch(`${EMULATOR}/emulator/v1/projects/${PROJECT}/databases/(default)/documents`, { method: "DELETE" });
  if (!res.ok) throw new Error(`No se pudo vaciar el emulador de Firestore (${res.status}). ¿Esta arriba enci-firestore-local?`);
  const env = { ...process.env, PATH: `${process.env.PATH};${DOCKER_BIN}` };
  for (const script of ["seed_admin.py", "seed_demo_fase4.py"]) {
    execSync(`docker exec enci-backend-local sh -c "PYTHONPATH=. uv run python scripts/${script}"`, { env, stdio: "pipe" });
  }
  await esperarApi();
}

/** `uv run` dentro del contenedor puede disparar el autoreload del servidor: se espera a que vuelva a responder. */
async function esperarApi(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 2500)); // deja que el reload empiece
  for (let i = 0; i < 40; i++) {
    try {
      if ((await fetch(`${API}/health`)).ok) return;
    } catch {
      /* el servidor se esta reiniciando */
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("La API no volvio a responder tras sembrar los datos");
}

export async function login(page: Page, user: { email: string; password: string }): Promise<void> {
  await page.goto("/login");
  await page.getByPlaceholder("Correo electrónico").fill(user.email);
  await page.getByPlaceholder("Contraseña").fill(user.password);
  await page.getByRole("button", { name: "Login" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/** RUT chileno valido con el digito verificador calculado (modulo 11). */
export function rutValido(body: number): string {
  let sum = 0;
  let factor = 2;
  for (const digit of String(body).split("").reverse()) {
    sum += Number(digit) * factor;
    factor = factor === 7 ? 2 : factor + 1;
  }
  const rest = 11 - (sum % 11);
  const dv = rest === 11 ? "0" : rest === 10 ? "K" : String(rest);
  return `${body}-${dv}`;
}

/** Token de la API (para preparar o comprobar datos sin pasar por la pantalla). */
export async function apiToken(user: { email: string; password: string }): Promise<string> {
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(user),
  });
  return (await res.json()).access_token;
}

export async function apiGet<T = any>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  return (await res.json()) as T;
}
