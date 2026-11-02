import { Page, expect } from '@playwright/test';

/**
 * Login como usuario autenticado (mock con JWT)
 * En producción, redirige a /login que autentica via /auth/login
 */
export async function loginAsDoctor(page: Page) {
  // Aquí irías a /login y completarías el flujo real
  // Por ahora, asumir que cookies/JWT ya están seteadas por el servidor
  // En desarrollo local, el backend ya devuelve la sesión
  await page.goto('/');
  await page.waitForLoadState('networkidle');
}

/**
 * Navega a la ficha de un paciente específico
 */
export async function navigateToPatient(page: Page, patientId: number) {
  await page.goto(`/pacientes/${patientId}/ficha`);
  await page.waitForLoadState('networkidle');
  // Esperar a que cargue la sección de Actos
  await expect(page.locator('text="Actos Clínicos"')).toBeVisible({ timeout: 5000 });
}

/**
 * Busca un paciente por nombre y abre su ficha
 */
export async function searchAndOpenPatient(page: Page, nombre: string) {
  await page.goto('/pacientes');
  await page.waitForLoadState('networkidle');

  // Búsqueda rápida
  const searchInput = page.locator('input[placeholder*="Buscar"]').first();
  await searchInput.fill(nombre);
  await page.waitForLoadState('networkidle');

  // Clic en primer resultado
  await page.locator('text=' + nombre).first().click();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text="Actos Clínicos"')).toBeVisible({ timeout: 5000 });
}

/**
 * Abre el flujo de consulta (detecta camino automáticamente)
 */
export async function abrirConsulta(page: Page) {
  const button = page.locator('button:has-text("Consulta")').first();
  await expect(button).toBeVisible();
  await button.click();
  await page.waitForTimeout(500); // Esperar a que se dispare la detección
}

/**
 * Espera a que aparezca un modal específico
 */
export async function waitForModal(page: Page, titulo: string) {
  await expect(page.locator(`text="${titulo}"`)).toBeVisible({ timeout: 5000 });
}

/**
 * Cierra un modal
 */
export async function closeModal(page: Page) {
  const closeButton = page.locator('button:has-text("Cerrar"), button:has-text("Cancelar")').first();
  if (await closeButton.isVisible()) {
    await closeButton.click();
    await page.waitForTimeout(300);
  }
}
