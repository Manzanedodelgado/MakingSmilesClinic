/**
 * Factories de datos de test — SIN faker, SIN aleatoriedad.
 *
 * Un paciente creado por un test:
 *  - lleva SIEMPRE el prefijo ZZ_E2E en nombre y apellidos,
 *  - lleva SIEMPRE nombre, apellidos, telefono_movil y fecha_nacimiento,
 *  - se registra en test-results/pacientes-creados.log,
 *  - debe borrarse con borrarPacienteTest() en el afterEach del test.
 */
import { APIRequestContext, expect } from '@playwright/test';
import { API, CENTRO_ID, E2E_PREFIX } from './constants';
import { registrarCreacion } from './database';

export interface PacienteCreado {
  id: number;
  num_historia: string;
  nombre: string;
  apellidos: string;
  telefono_movil: string;
  fecha_nacimiento: string;
  email: string;
}

/** Sufijo único y estable por ejecución (no aleatorio: deriva del reloj de arranque). */
const RUN_TAG = new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14);
let _seq = 0;

/**
 * NumPac reservado para pacientes E2E. Rango 900000000+ (9 dígitos): fuera de cualquier
 * NumPac real de la clínica, y derivado del reloj+secuencia para no colisionar ni entre
 * workers paralelos ni entre ejecuciones. El backend auto-asigna NumPac si no se envía,
 * y dos POST concurrentes reciben el mismo -> 409; enviarlo explícito lo evita.
 */
function numHistoriaE2E(): string {
  const base = 900_000_000;
  const t = Number(new Date().toISOString().slice(11, 23).replace(/[:.]/g, '')); // HHMMSSmmm
  return String(base + (t % 90_000_000) + _seq);
}

export class PacienteFactory {
  /**
   * Crea un paciente real vía POST /pacientes/nuevo y lo registra en el log.
   * @param request  APIRequestContext autenticado (fixture `request` de Playwright).
   */
  static async crear(request: APIRequestContext): Promise<PacienteCreado> {
    _seq += 1;
    const marca = `${RUN_TAG}-${_seq}`;
    const payload = {
      nombre: `${E2E_PREFIX} Nombre ${marca}`,
      apellidos: `${E2E_PREFIX} Apellidos ${marca}`,
      num_historia: numHistoriaE2E(),
      telefono_movil: '600000000',
      fecha_nacimiento: '1990-01-01',
      email: `zz-e2e-${marca}@test.local`,
    };

    const resp = await request.post(`${API}/pacientes/nuevo`, {
      data: payload,
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
    });
    expect(
      resp.status(),
      `POST /pacientes/nuevo devolvió ${resp.status()}: ${await resp.text()}`
    ).toBe(201);

    const body = await resp.json();
    const id: number = body.id;
    registrarCreacion('paciente', id, `num_historia=${body.num_historia} ${payload.nombre}`);

    return {
      id,
      num_historia: String(body.num_historia ?? ''),
      nombre: payload.nombre,
      apellidos: payload.apellidos,
      telefono_movil: payload.telefono_movil,
      fecha_nacimiento: payload.fecha_nacimiento,
      email: payload.email,
    };
  }
}
