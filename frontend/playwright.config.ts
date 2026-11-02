import { defineConfig, devices } from '@playwright/test';
import path from 'path';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.spec.ts',

  // ✅ Paralelo SOLO en tests que son aislados
  // Paso 9 usa mode: 'serial' internamente
  fullyParallel: true,

  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,

  // CI: 1 worker | Local: auto-detectar CPUs
  workers: process.env.CI ? 1 : undefined,

  reporter: [
    ['html'],
    ['json', { outputFile: 'test-results/results.json' }],
  ],

  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  // ✅ Usar auth state del global.setup
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // storageState disabled for simplified test (no auth)
      },
    },
  ],

  // ✅ Global setup: autenticación previa
  // globalSetup: disabled for simplified test (no DB)
  // ✅ Global teardown: purga de pacientes ZZ_E2E huérfanos
  globalTeardown: require.resolve('./e2e/global.teardown.ts'),

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },

  timeout: 30000,
  expect: {
    timeout: 5000,
  },
});
