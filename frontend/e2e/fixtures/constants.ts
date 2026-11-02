/**
 * Constantes compartidas de la suite E2E.
 *
 * Los valores REALES (contraseña de la BD, datos del paciente de pruebas) NO viven
 * aquí: se leen de  e2e/.env.e2e  (git-ignored). Copia  e2e/.env.e2e.example  a
 * e2e/.env.e2e  y rellénalo. Sin ese fichero, la suite usa placeholders y fallará
 * al conectar con la BD — que es lo correcto: nunca datos reales en el repo.
 *
 * REGLA DE DATOS (definida por el usuario):
 *  - Lecturas / navegación / búsquedas → SIEMPRE el paciente real (E2E_PACIENTE_*).
 *  - Crear / editar / borrar → paciente NUEVO vía POST /pacientes/nuevo,
 *    registrado en el log de creaciones y borrado al final del test.
 *  - Nunca se modifica ni se borra el paciente real.
 *  - Cero faker / cero datos aleatorios.
 */
import * as fs from 'fs';
import * as path from 'path';

/** Carga e2e/.env.e2e (KEY=VALUE por línea, # comentarios) en process.env. Sin dependencias. */
function cargarEnvE2E(): void {
  const f = path.join(__dirname, '..', '.env.e2e');
  let txt: string;
  try {
    txt = fs.readFileSync(f, 'utf8');
  } catch {
    console.warn(
      '[e2e] No se encontró e2e/.env.e2e — usando placeholders. ' +
      'Copia e2e/.env.e2e.example y rellénalo para correr la suite.'
    );
    return;
  }
  for (const linea of txt.split('\n')) {
    const s = linea.trim();
    if (!s || s.startsWith('#')) continue;
    const i = s.indexOf('=');
    if (i === -1) continue;
    const k = s.slice(0, i).trim();
    const v = s.slice(i + 1).trim();
    if (!(k in process.env)) process.env[k] = v;
  }
}
cargarEnvE2E();

const env = (k: string, def = ''): string => process.env[k] ?? def;
const envN = (k: string, def = 0): number => {
  const v = process.env[k];
  return v === undefined || v === '' ? def : Number(v);
};

export const API = env('E2E_API_URL', 'http://localhost:8000');
export const BASE_URL = env('E2E_BASE_URL', 'http://localhost:3000');
export const CENTRO_ID = envN('E2E_CENTRO_ID', 1);
export const ROL_ID = envN('E2E_ROL_ID', 1);

export const TEST_USER = {
  email: env('E2E_TEST_EMAIL', 'test@example.test'),
  password: env('E2E_TEST_PASSWORD', 'changeme'),
} as const;

/**
 * Paciente real de pruebas — solo lectura. `id` = clave interna (rutas
 * /pacientes/{id}); `numHistoria` = NumPac visible. Valores en e2e/.env.e2e.
 */
export const PACIENTE_REAL = {
  id: envN('E2E_PACIENTE_ID', 0),
  numHistoria: env('E2E_PACIENTE_NUM_HISTORIA', '0000'),
  nombre: env('E2E_PACIENTE_NOMBRE', 'NOMBRE'),
  apellidos: env('E2E_PACIENTE_APELLIDOS', 'APELLIDOS'),
  nif: env('E2E_PACIENTE_NIF', '00000000X'),
  telefonoMovil: env('E2E_PACIENTE_MOVIL', '600000000'),
  telefonoFijo: env('E2E_PACIENTE_FIJO', '900000000'),
  email: env('E2E_PACIENTE_EMAIL', 'paciente@example.test'),
} as const;

/**
 * Prefijo obligatorio en nombre/apellidos de todo paciente creado por los tests.
 * Permite identificar y purgar restos si un afterEach no llegó a ejecutarse.
 */
export const E2E_PREFIX = 'ZZ_E2E';

/** Colaborador (doctor) real del centro — necesario en actos, presupuestos y consulta. */
export const COLABORADOR_REAL = {
  id: envN('E2E_COLABORADOR_ID', 0),
  nombre: env('E2E_COLABORADOR_NOMBRE', 'NOMBRE DOCTOR'),
} as const;

/** Tratamiento real del catálogo del centro — necesario para líneas de presupuesto. */
export const TRATAMIENTO_REAL = {
  id: envN('E2E_TRATAMIENTO_ID', 0),
  nombre: env('E2E_TRATAMIENTO_NOMBRE', 'TRATAMIENTO'),
  precio: envN('E2E_TRATAMIENTO_PRECIO', 0),
} as const;

/** Conexión a la BD real de auditoría — credenciales en e2e/.env.e2e (git-ignored). */
export const DB = {
  host: env('E2E_DB_HOST', 'localhost'),
  port: envN('E2E_DB_PORT', 5433),
  database: env('E2E_DB_NAME', 'makingsmiles'),
  user: env('E2E_DB_USER', 'makingsmiles'),
  password: env('E2E_DB_PASSWORD', ''),
} as const;
