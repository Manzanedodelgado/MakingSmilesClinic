/**
 * Acceso directo a la BD real para preparación y limpieza de datos de test.
 * La API NO expone DELETE de paciente, así que el borrado es SQL directo.
 */
import { Pool } from 'pg';
import * as fs from 'fs';
import * as path from 'path';
import { DB, E2E_PREFIX } from './constants';

const pool = new Pool(DB);

/** Log append-only de todo lo que los tests crean, para trazabilidad y purga manual.
 *  __dirname = e2e/fixtures  ->  frontend/test-results/pacientes-creados.log */
const LOG_PATH = path.join(__dirname, '..', '..', 'test-results', 'pacientes-creados.log');

export function registrarCreacion(entidad: string, id: number | string, detalle = ''): void {
  const linea = `${new Date().toISOString()}\t${entidad}\tid=${id}\t${detalle}\n`;
  try {
    fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });
    fs.appendFileSync(LOG_PATH, linea);
  } catch {
    // el log es best-effort; no debe tumbar un test
  }
}

/** Tablas con FK -> pacientes.id, descubiertas una sola vez. */
let _tablasDependientes: Array<{ tabla: string; columna: string }> | null = null;

async function tablasQueReferencianPacientes(): Promise<Array<{ tabla: string; columna: string }>> {
  if (_tablasDependientes !== null) return _tablasDependientes;
  const client = await pool.connect();
  try {
    const { rows } = await client.query(`
      SELECT tc.table_name AS tabla, kcu.column_name AS columna
      FROM information_schema.table_constraints tc
      JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
      JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
      WHERE tc.constraint_type = 'FOREIGN KEY'
        AND ccu.table_name = 'pacientes'
        AND ccu.column_name = 'id'
        AND tc.table_name <> 'pacientes'
    `);
    _tablasDependientes = rows.map((r: { tabla: string; columna: string }) => ({
      tabla: r.tabla,
      columna: r.columna,
    }));
    return _tablasDependientes;
  } finally {
    client.release();
  }
}

/**
 * Borra un paciente creado por los tests y TODAS sus dependencias.
 * Rechaza el borrado si el nombre no lleva el prefijo E2E (salvaguarda anti-accidente).
 */
export async function borrarPacienteTest(pacienteId: number): Promise<void> {
  const client = await pool.connect();
  try {
    const { rows } = await client.query(
      'SELECT nombre, apellidos FROM pacientes WHERE id = $1',
      [pacienteId]
    );
    if (rows.length === 0) return; // ya no existe
    const { nombre, apellidos } = rows[0];
    if (!`${nombre} ${apellidos}`.includes(E2E_PREFIX)) {
      throw new Error(
        `SEGURIDAD: rehúso borrar paciente ${pacienteId} ("${nombre} ${apellidos}") ` +
        `— no lleva el prefijo ${E2E_PREFIX}. Un test intentó borrar un paciente real.`
      );
    }

    const deps = await tablasQueReferencianPacientes();
    await client.query('BEGIN');

    // Ejecuta un DELETE dentro de su propio savepoint: si falla (p. ej. una FK que aún
    // no se puede resolver), se revierte SOLO ese statement y la transacción sigue viva.
    const delSeguro = async (sql: string): Promise<boolean> => {
      await client.query('SAVEPOINT sp');
      try {
        await client.query(sql, [pacienteId]);
        await client.query('RELEASE SAVEPOINT sp');
        return true;
      } catch (e: any) {
        await client.query('ROLLBACK TO SAVEPOINT sp');
        await client.query('RELEASE SAVEPOINT sp');
        if (/does not exist/.test(e.message)) return true; // tabla/columna ausente: nada que borrar
        return false;
      }
    };

    // "Nietos" conocidos: filas que cuelgan de una tabla hija, no de pacientes.
    const nietos = [
      `DELETE FROM presupuesto_lineas WHERE presupuesto_id IN (SELECT id FROM presupuestos WHERE paciente_id = $1)`,
      `DELETE FROM receta_lineas WHERE receta_id IN (SELECT id FROM recetas WHERE paciente_id = $1)`,
      `DELETE FROM soap WHERE cita_id IN (SELECT id FROM citas WHERE paciente_id = $1)`,
      `DELETE FROM hallazgos_imagen WHERE imagen_id IN (SELECT id FROM imagenes_rx WHERE paciente_id = $1)`,
      `DELETE FROM anotaciones_imagen WHERE imagen_id IN (SELECT id FROM imagenes_rx WHERE paciente_id = $1)`,
      `DELETE FROM cefalometrias WHERE imagen_id IN (SELECT id FROM imagenes_rx WHERE paciente_id = $1)`,
    ];
    for (const sql of nietos) await delSeguro(sql);

    // Borrado por cada FK -> pacientes.id, en varias pasadas para absorber dependencias
    // entre estas tablas sin ordenarlas a mano. Cada intento va en su savepoint.
    let pendientes = deps.map((d) => `DELETE FROM "${d.tabla}" WHERE "${d.columna}" = $1`);
    for (let pasada = 0; pasada < 5 && pendientes.length; pasada++) {
      const fallidas: string[] = [];
      for (const sql of pendientes) {
        if (!(await delSeguro(sql))) fallidas.push(sql);
      }
      if (fallidas.length === pendientes.length) break; // sin progreso: aborta el bucle
      pendientes = fallidas;
    }
    if (pendientes.length) {
      throw new Error(
        `No se pudieron limpiar dependencias del paciente ${pacienteId}:\n` +
        pendientes.join('\n')
      );
    }

    await delSeguro('DELETE FROM citas WHERE tutor_id = $1');
    await client.query('UPDATE pacientes SET tutor_id = NULL WHERE tutor_id = $1', [pacienteId]);
    await client.query('DELETE FROM pacientes WHERE id = $1', [pacienteId]);
    await client.query('COMMIT');
  } catch (e) {
    await client.query('ROLLBACK').catch(() => {});
    throw e;
  } finally {
    client.release();
  }
}

/**
 * Borra los documentos administrativos (facturas, etc.) creados por los tests.
 * documentos_admin guarda la identidad inline por nombre — no tiene FK a pacientes,
 * así que borrarPacienteTest no los alcanza.
 */
export async function borrarDocumentosTest(): Promise<number> {
  const client = await pool.connect();
  try {
    const { rowCount } = await client.query(
      `DELETE FROM documentos_admin WHERE nombre LIKE $1 OR apellidos LIKE $1`,
      [`%${E2E_PREFIX}%`]
    );
    return rowCount ?? 0;
  } finally {
    client.release();
  }
}

/** Borra claves de configuración, gastos, movimientos y plantillas dejados por los tests. */
export async function borrarMiscTest(): Promise<void> {
  const client = await pool.connect();
  try {
    const limpiezas = [
      `DELETE FROM configuraciones WHERE clave LIKE 'zz_e2e%'`,
      `DELETE FROM gastos WHERE concepto LIKE $1`,
      `DELETE FROM movimientos_bancarios WHERE concepto_banco LIKE $1`,
      `DELETE FROM presupuestos_predisenados WHERE titulo LIKE $1`,
      `DELETE FROM informes WHERE nombre LIKE $1`,
      `DELETE FROM plantillas_mensaje WHERE nombre LIKE $1`,
    ];
    for (const sql of limpiezas) {
      await client
        .query(sql, sql.includes('$1') ? [`%${E2E_PREFIX}%`] : [])
        .catch((e: any) => {
          if (!/does not exist/.test(e.message)) throw e;
        });
    }
  } finally {
    client.release();
  }
}

/** Purga cualquier paciente E2E huérfano (por si un afterEach falló). Se llama en globalTeardown. */
export async function purgarPacientesE2E(): Promise<number> {
  const client = await pool.connect();
  try {
    const { rows } = await client.query(
      `SELECT id FROM pacientes WHERE nombre LIKE $1 OR apellidos LIKE $1`,
      [`%${E2E_PREFIX}%`]
    );
    for (const { id } of rows) {
      await borrarPacienteTest(id).catch((e) => console.error(`purga id=${id}:`, e.message));
    }
    return rows.length;
  } finally {
    client.release();
  }
}

export async function getPacienteFromDB(pacienteId: number): Promise<any | null> {
  const client = await pool.connect();
  try {
    const { rows } = await client.query('SELECT * FROM pacientes WHERE id = $1', [pacienteId]);
    return rows[0] ?? null;
  } finally {
    client.release();
  }
}

export async function closePool(): Promise<void> {
  await pool.end();
}
