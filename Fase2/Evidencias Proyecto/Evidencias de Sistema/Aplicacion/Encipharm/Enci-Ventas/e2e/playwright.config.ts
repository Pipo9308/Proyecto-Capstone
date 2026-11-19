import { defineConfig } from "@playwright/test";

// Edge ya viene instalado en Windows: no hace falta descargar navegadores. En CI/Linux: `npx playwright install chromium`
// y E2E_BROWSER_CHANNEL= (vacio).
const channel = process.env.E2E_BROWSER_CHANNEL ?? "msedge";

export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // Todos los tests comparten la misma base (el emulador): se corren de a uno.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    channel: channel || undefined,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "es-CL",
    timezoneId: "America/Santiago",
  },
});
