import { defineConfig } from "@playwright/test";

/** Pruebas visuales contra una app ya en marcha (sin globalSetup ni base de datos): `npm run test:visual`.
 *  Variables: MS_BASE (por defecto http://localhost:3000), MS_EMAIL y MS_PASS (usuario de pruebas). */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.visual.ts",
  reporter: "list",
  timeout: 120_000,
  use: { channel: "chrome", baseURL: process.env.MS_BASE ?? "http://localhost:3000" },
});
