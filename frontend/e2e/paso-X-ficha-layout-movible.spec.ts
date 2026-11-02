/**
 * Ficha de paciente — cajas movibles/redimensionables.
 * Sin mocks. Contra backend + Postgres reales. Paciente real de lectura: PACIENTE_REAL.
 * El usuario de la sesión (e2e/.auth/user.json) es rol Administrador → tiene config.editar,
 * así que cubre el camino "puede reorganizar" de punta a punta.
 */
import { test, expect } from '@playwright/test';
import { Pool } from 'pg';
import { API, BASE_URL, CENTRO_ID, DB, PACIENTE_REAL } from './fixtures/constants';

const pool = new Pool(DB);

test.describe('Ficha de paciente: layout movible', () => {
  test.afterEach(async ({ request }) => {
    // Deja la clave en un estado conocido para no contaminar otros tests/gente probando a mano.
    await request.put(`${API}/config`, {
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
      data: { clave: 'ficha_layout', valor: null, sistema: 'pacientes' },
    }).catch(() => {});
  });

  test('admin: reorganiza, guarda, y persiste tras recargar', async ({ page }) => {
    await page.goto(`${BASE_URL}/pacientes/${PACIENTE_REAL.id}/ficha`);
    await expect(page.getByRole('button', { name: /reorganizar cajas/i })).toBeVisible();

    await page.getByRole('button', { name: /reorganizar cajas/i }).click();
    const tirador = page.locator('.caja-drag-handle').first();
    await expect(tirador).toBeVisible();

    // Arrastra la primera caja ~150px a la derecha.
    const box = await tirador.boundingBox();
    if (!box) throw new Error('No se pudo medir el tirador');
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 150, box.y + box.height / 2, { steps: 10 });
    await page.mouse.up();

    await page.getByRole('button', { name: /guardar disposición/i }).click();
    await expect(page.getByRole('button', { name: /reorganizar cajas/i })).toBeVisible();

    // Confirma en BD que quedó guardado con los 4 ids esperados.
    const { rows } = await pool.query(
      `SELECT valor FROM configuraciones WHERE clave = 'ficha_layout' AND sistema = 'pacientes' AND centro_id = $1`,
      [CENTRO_ID],
    );
    expect(rows).toHaveLength(1);
    const ids = (rows[0].valor as Array<{ i: string }>).map((it) => it.i).sort();
    expect(ids).toEqual(['historial', 'multimedia', 'nuevo_acto', 'odontograma']);

    // Recarga → sigue sin el botón "Guardar" activo (modo edición se cerró) y sin errores visibles.
    await page.reload();
    await expect(page.getByRole('button', { name: /reorganizar cajas/i })).toBeVisible();
    await expect(page.locator('.caja-drag-handle')).toHaveCount(0);
  });

  test('sin permiso config.editar: no ve el botón ni los tiradores', async ({ page }) => {
    // IMPORTANTE: los permisos efectivos NO salen del rol (role_permisos) — AuthService.permisos_de
    // (backend/application/services/auth_service.py:174-185) resuelve SOLO por concesión directa en
    // user_center_permisos (usuario_id × centro_id × permiso_id). Por eso se quita de ahí, no del rol.
    const usuarioRow = await pool.query(
      `SELECT id FROM usuarios WHERE email = $1`,
      [process.env.E2E_TEST_EMAIL ?? 'test@example.test'],
    );
    const usuarioId = usuarioRow.rows[0].id;
    const permisoRow = await pool.query(`SELECT id FROM permisos WHERE codigo = 'config.editar'`);
    const permisoId = permisoRow.rows[0].id;

    await pool.query(
      `DELETE FROM user_center_permisos WHERE usuario_id = $1 AND centro_id = $2 AND permiso_id = $3`,
      [usuarioId, CENTRO_ID, permisoId],
    );
    try {
      await page.goto(`${BASE_URL}/pacientes/${PACIENTE_REAL.id}/ficha`);
      await expect(page.getByRole('button', { name: /reorganizar cajas/i })).toHaveCount(0);
      await expect(page.locator('.caja-drag-handle')).toHaveCount(0);
    } finally {
      // Restaura la concesión directa — si no, el resto de la suite se queda sin config.editar.
      await pool.query(
        `INSERT INTO user_center_permisos (usuario_id, centro_id, permiso_id) VALUES ($1, $2, $3)
         ON CONFLICT DO NOTHING`,
        [usuarioId, CENTRO_ID, permisoId],
      );
    }
  });
});
