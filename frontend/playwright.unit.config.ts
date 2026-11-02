import { defineConfig } from "@playwright/test";

/** Tests unitarios (sin navegador): `npm run test:unit`. Los e2e reales viven en e2e/ con playwright.config.ts. */
export default defineConfig({
  testDir: "./src",
  testMatch: "**/*.unit.ts",
  reporter: "list",
});
