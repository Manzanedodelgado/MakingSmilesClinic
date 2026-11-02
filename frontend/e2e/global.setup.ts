import { chromium, FullConfig } from '@playwright/test';
import { Pool } from 'pg';
import { DB, API, BASE_URL, CENTRO_ID, ROL_ID, TEST_USER } from './fixtures/constants';

const pool = new Pool(DB);

// Centro y rol contra los que se autentican los tests (valores en e2e/.env.e2e).
// El centro 1 existe en la BD de auditoría (RUBIO GARCIA DENTAL); el rol 1 es "Administrador".
const TEST_CENTRO_ID = CENTRO_ID;
const TEST_ROL_ID = ROL_ID;

async function ensureTestUser(): Promise<{ email: string; password: string }> {
  const client = await pool.connect();
  try {
    const testEmail = TEST_USER.email;
    const testPassword = TEST_USER.password;

    await client.query('BEGIN');

    // 1. Usuario (identidad global). Reescribimos SIEMPRE el hash para que el setup
    //    sea idempotente aunque alguien lo haya cambiado en una corrida anterior.
    const { rows } = await client.query(
      'SELECT id FROM usuarios WHERE email = $1',
      [testEmail]
    );
    let usuarioId: number;
    if (rows.length === 0) {
      const ins = await client.query(
        `INSERT INTO usuarios (email, password_hash, nombre, created_at, updated_at)
         VALUES ($1, crypt($2, gen_salt('bf')), $3, NOW(), NOW())
         RETURNING id`,
        [testEmail, testPassword, 'Test Admin']
      );
      usuarioId = ins.rows[0].id;
      console.log('✅ Usuario test creado (id ' + usuarioId + ')');
    } else {
      usuarioId = rows[0].id;
      await client.query(
        `UPDATE usuarios
            SET password_hash = crypt($2, gen_salt('bf')), updated_at = NOW()
          WHERE id = $1`,
        [usuarioId, testPassword]
      );
      console.log('✅ Usuario test ya existe (id ' + usuarioId + '), hash reseteado');
    }

    // 2. Periodo laboral ABIERTO en el centro de test. AuthService._usuario_activo_por_email
    //    exige un usuario_periodos con fecha_baja NULL o futura; sin esto el login da 401.
    const per = await client.query(
      `SELECT id FROM usuario_periodos
        WHERE usuario_id = $1 AND centro_id = $2 AND fecha_baja IS NULL`,
      [usuarioId, TEST_CENTRO_ID]
    );
    if (per.rows.length === 0) {
      await client.query(
        `INSERT INTO usuario_periodos
           (usuario_id, centro_id, orden, staff_tipo, tipo_contrato,
            fecha_alta, fecha_baja, created_at, updated_at)
         VALUES ($1, $2, 0, 'DOCTOR', 'Reg. General', CURRENT_DATE, NULL, NOW(), NOW())`,
        [usuarioId, TEST_CENTRO_ID]
      );
      console.log('✅ Periodo laboral abierto creado');
    }

    // 3. Membresía (acceso al centro) — construye `accesos` en el JWT.
    await client.query(
      `INSERT INTO user_center_roles
         (usuario_id, centro_id, rol_id, created_at, updated_at)
       SELECT $1, $2, $3, NOW(), NOW()
        WHERE NOT EXISTS (
          SELECT 1 FROM user_center_roles
           WHERE usuario_id = $1 AND centro_id = $2
        )`,
      [usuarioId, TEST_CENTRO_ID, TEST_ROL_ID]
    );

    // 4. Permisos finos (ya NO derivan del rol_id, sino de user_center_permisos).
    //    Concedemos TODOS los permisos existentes para que ningún test real quede
    //    bloqueado por 403 — incluido superuser y gestoria.facturacion.ver.
    await client.query(
      `INSERT INTO user_center_permisos
         (usuario_id, centro_id, permiso_id, created_at, updated_at)
       SELECT $1, $2, p.id, NOW(), NOW()
         FROM permisos p
        WHERE NOT EXISTS (
          SELECT 1 FROM user_center_permisos ucp
           WHERE ucp.usuario_id = $1 AND ucp.centro_id = $2 AND ucp.permiso_id = p.id
        )`,
      [usuarioId, TEST_CENTRO_ID]
    );

    // 5. Colaborador ligado al periodo del usuario test. Sin esto, consulta/cerrar,
    //    recetas y cualquier flujo que registre un acto fallan con
    //    "El usuario no tiene colaborador asociado".
    const { rows: perRows } = await client.query(
      `SELECT id FROM usuario_periodos
        WHERE usuario_id = $1 AND centro_id = $2 AND fecha_baja IS NULL
        ORDER BY id DESC LIMIT 1`,
      [usuarioId, TEST_CENTRO_ID]
    );
    const periodoId = perRows[0]?.id;
    if (periodoId) {
      await client.query(
        `INSERT INTO colaboradores
           (periodo_id, activo, aplica_laboratorio, aplica_irpf, factura_produccion,
            num_colegiado, created_at, updated_at)
         SELECT $1, TRUE, FALSE, FALSE, FALSE, 'E2E-0000', NOW(), NOW()
          WHERE NOT EXISTS (SELECT 1 FROM colaboradores WHERE periodo_id = $1)`,
        [periodoId]
      );
    }

    await client.query('COMMIT');
    console.log('✅ Grafo de acceso del usuario test garantizado (periodo + rol + permisos + colaborador)');

    return { email: testEmail, password: testPassword };
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}

async function globalSetup(config: FullConfig) {
  try {
    // 1. Garantizar usuario admin dinámicamente
    console.log('🔐 Garantizando usuario admin de prueba...');
    const credentials = await ensureTestUser();

    const browser = await chromium.launch();
    const page = await browser.newPage();

    try {
      console.log('🔐 Autenticando vía API (evitando UI)...');

      // 2. Autenticación directa vía API (más confiable que UI)
      const loginResponse = await page.request.post(
        `${API}/auth/login`,
        {
          data: {
            email: credentials.email,
            password: credentials.password
          }
        }
      );

      if (![200, 201].includes(loginResponse.status())) {
        throw new Error(`Login failed: ${loginResponse.status()}`);
      }

      const loginData = await loginResponse.json();
      const token = loginData.access_token || loginData.token;

      if (!token) {
        throw new Error('No token received from login');
      }

      console.log('✅ Autenticación API exitosa');

      // 3. Establecer token en el contexto del navegador. El backend lee la cookie
      //    `access_token` (ver api/auth_router.py) — el nombre debe coincidir exactamente.
      await page.context().addCookies([
        {
          name: 'access_token',
          value: token,
          domain: 'localhost',
          path: '/',
          httpOnly: true,
          sameSite: 'Lax',
          expires: Date.now() / 1000 + 60 * 60 * 24 // 1 day from now
        }
      ]);

      // 4. Navegar a una ruta protegida para verificar autenticación
      await page.goto(`${BASE_URL}/pacientes`, { waitUntil: 'networkidle' });

      // 5. Verificar que el token realmente da acceso a una ruta protegida real.
      //    /auth/me es el check canónico: 200 con token válido, 401 sin él.
      const userResponse = await page.request.get(`${API}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (userResponse.status() !== 200) {
        throw new Error(
          `Failed to access protected route after login: ${userResponse.status()}`
        );
      }

      // 6. Guardar storage state (cookies + localStorage)
      await page.context().storageState({ path: 'e2e/.auth/user.json' });

      console.log('✅ Autenticación completada. Estado guardado en e2e/.auth/user.json');
    } finally {
      await browser.close();
    }
  } finally {
    await pool.end();
  }
}

export default globalSetup;
