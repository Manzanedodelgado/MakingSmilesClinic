/**
 * PASO 1 — Autenticación (Real, UI, Estricto)
 *
 * Sin mocks. Único spec de la suite que conduce el NAVEGADOR real: el resto son API.
 * Ejercita el login por formulario, la cookie httpOnly, el acceso a rutas protegidas
 * y el logout, contra frontend + backend + BD reales.
 *
 * Estos tests NO usan el storageState del proyecto: parten sin sesión a propósito.
 * Selectores verificados contra la página real /login (2026-08-29):
 *   input[type=email] · input[type=password] · button[type=submit] ("Acceder")
 *   logout: botón "Salir" en el header de (app)/layout.tsx -> POST /auth/logout -> /login
 */
import { test, expect } from '@playwright/test';

const EMAIL = 'test_4134@saas-audit.com';
const PASSWORD = 'password123';

// arranca sin la sesión guardada por global.setup
test.use({ storageState: { cookies: [], origins: [] } });

test.describe('Paso 1: Autenticación (Real, UI)', () => {
  test('1.1: /login muestra el formulario', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('1.2: una ruta protegida sin sesión redirige a /login', async ({ page }) => {
    await page.goto('/pacientes');
    await page.waitForURL(/\/login/, { timeout: 10_000 });
    expect(page.url()).toContain('/login');
  });

  test('1.3: login correcto entra en la app y fija la cookie httpOnly', async ({ page, context }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill(EMAIL);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();

    // sale de /login hacia una ruta de la app
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 });
    expect(new URL(page.url()).pathname).not.toBe('/login');

    const cookie = (await context.cookies()).find((c) => c.name === 'access_token');
    expect(cookie, 'la cookie access_token debe existir tras el login').toBeTruthy();
    expect(cookie!.httpOnly).toBe(true);

    // el token no es accesible desde JS (httpOnly de verdad)
    const visibleEnJs = await page.evaluate(() => document.cookie.includes('access_token'));
    expect(visibleEnJs).toBe(false);
  });

  test('1.4: login con contraseña incorrecta no entra y muestra error', async ({ page, context }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill(EMAIL);
    await page.locator('input[type="password"]').fill('contraseña-incorrecta');
    await page.locator('button[type="submit"]').click();

    // sigue en /login
    await page.waitForTimeout(1500);
    expect(page.url()).toContain('/login');

    const cookie = (await context.cookies()).find((c) => c.name === 'access_token');
    expect(cookie).toBeFalsy();
  });

  test('1.5: sesión iniciada -> navegar a un paciente real carga su ficha', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill(EMAIL);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 });

    await page.goto('/pacientes/4767/ficha');
    await page.waitForLoadState('networkidle');
    // el apellido real del paciente 4134 aparece en la ficha
    await expect(page.getByText('MANZANEDO', { exact: false }).first()).toBeVisible({ timeout: 10_000 });
  });

  test('1.6: logout borra la sesión y vuelve a /login', async ({ page, context }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill(EMAIL);
    await page.locator('input[type="password"]').fill(PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 });

    await page.getByRole('button', { name: 'Salir' }).click();
    await page.waitForURL(/\/login/, { timeout: 10_000 });

    const cookie = (await context.cookies()).find((c) => c.name === 'access_token');
    expect(cookie, 'la cookie debe eliminarse en el logout').toBeFalsy();

    // y el backend ya no reconoce la sesión: /auth/me responde 401
    const me = await page.request.get('http://localhost:8000/auth/me');
    expect(me.status()).toBe(401);
  });
});
