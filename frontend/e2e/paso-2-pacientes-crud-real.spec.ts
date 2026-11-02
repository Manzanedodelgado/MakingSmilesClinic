/**
 * PASO 2 — Pacientes CRUD (Real, Aislado, Estricto)
 *
 * Sin mocks. Contra backend + Postgres reales.
 * Datos:
 *   - lecturas / búsquedas  -> paciente real 4134 (PACIENTE_REAL)
 *   - crear / editar         -> paciente nuevo ZZ_E2E, borrado en afterEach
 *
 * Contrato real verificado en /openapi.json (2026-08-29):
 *   GET  /pacientes/{id}                -> 200 {id,num_historia,nombre,apellidos,nif,edad,telefono_movil,...}
 *   PUT  /pacientes/{id}                -> 200 {id}
 *   GET  /pacientes/buscar?q=           -> 200 {pacientes:[{id,num_historia,nombre,apellidos,nif,telefono}]}
 *   GET  /pacientes/{id}/filiacion      -> 200 {num_historia,nombre,apellidos,direccion,cp,telefono_movil,email,...}
 *   GET  /pacientes/{id}/ficha          -> 200
 *   POST /pacientes/nuevo               -> 201 {id,num_historia,romexis_sync_id}
 *   (NO existe GET /pacientes colección, NO existe DELETE /pacientes/{id})
 */
import { test, expect } from '@playwright/test';
import { API, CENTRO_ID, PACIENTE_REAL } from './fixtures/constants';
import { PacienteFactory } from './fixtures/factories';
import { borrarPacienteTest } from './fixtures/database';

test.describe('Paso 2: Pacientes CRUD (Real, Aislado, Estricto)', () => {
  let pacienteCreadoId: number | null = null;

  test.afterEach(async () => {
    if (pacienteCreadoId) {
      await borrarPacienteTest(pacienteCreadoId);
      pacienteCreadoId = null;
    }
  });

  test('2.1: GET /pacientes/{id} retorna el paciente real 4134', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${PACIENTE_REAL.id}`, {
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
    });
    expect(resp.status()).toBe(200);

    const data = await resp.json();
    expect(data.id).toBe(PACIENTE_REAL.id);
    expect(data.num_historia).toBe(PACIENTE_REAL.numHistoria);
    expect(data.nombre).toBe(PACIENTE_REAL.nombre);
    expect(data.apellidos).toBe(PACIENTE_REAL.apellidos);
    expect(data.telefono_movil).toBe(PACIENTE_REAL.telefonoMovil);
  });

  test('2.2: GET /pacientes/{id} retorna 404 si no existe', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/99999999`, {
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
    });
    expect(resp.status()).toBe(404);
  });

  test('2.3: GET /pacientes/buscar encuentra al paciente real por apellido', async ({ request }) => {
    const resp = await request.get(
      `${API}/pacientes/buscar?q=${encodeURIComponent('MANZANEDO DELGADO')}`,
      { headers: { 'X-Centro-Id': String(CENTRO_ID) } }
    );
    expect(resp.status()).toBe(200);

    const body = await resp.json();
    expect(Array.isArray(body.pacientes)).toBe(true);
    expect(body.pacientes.some((p: any) => p.id === PACIENTE_REAL.id)).toBe(true);
  });

  test('2.4: GET /pacientes/buscar encuentra al paciente real por num_historia', async ({ request }) => {
    const resp = await request.get(
      `${API}/pacientes/buscar?q=${PACIENTE_REAL.numHistoria}`,
      { headers: { 'X-Centro-Id': String(CENTRO_ID) } }
    );
    expect(resp.status()).toBe(200);

    const body = await resp.json();
    expect(
      body.pacientes.some((p: any) => p.num_historia === PACIENTE_REAL.numHistoria)
    ).toBe(true);
  });

  test('2.5: GET /pacientes/{id}/filiacion devuelve la filiación real', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${PACIENTE_REAL.id}/filiacion`, {
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
    });
    expect(resp.status()).toBe(200);

    const data = await resp.json();
    expect(data.num_historia).toBe(PACIENTE_REAL.numHistoria);
    expect(data.nombre).toBe(PACIENTE_REAL.nombre);
    expect(data.email).toBe(PACIENTE_REAL.email);
    expect(data.telefono_movil).toBe(PACIENTE_REAL.telefonoMovil);
  });

  test('2.6: GET /pacientes/{id}/ficha responde 200 para el paciente real', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${PACIENTE_REAL.id}/ficha`, {
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
    });
    expect(resp.status()).toBe(200);
  });

  test('2.7: POST /pacientes/nuevo crea un paciente y persiste en BD', async ({ request }) => {
    const p = await PacienteFactory.crear(request);
    pacienteCreadoId = p.id;

    expect(p.id).toBeGreaterThan(0);
    expect(p.num_historia).not.toBe('');

    const resp = await request.get(`${API}/pacientes/${p.id}`, {
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.nombre).toBe(p.nombre);
    expect(data.apellidos).toBe(p.apellidos);
    expect(data.telefono_movil).toBe(p.telefono_movil);
  });

  test('2.8: PUT /pacientes/{id} edita el paciente creado y persiste', async ({ request }) => {
    const p = await PacienteFactory.crear(request);
    pacienteCreadoId = p.id;

    const nuevoTelefono = '611222333';
    const nuevasNotas = 'ZZ_E2E editado en test 2.8';
    const put = await request.put(`${API}/pacientes/${p.id}`, {
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
      data: { telefono_movil: nuevoTelefono, notas: nuevasNotas },
    });
    expect(put.status()).toBe(200);

    const check = await request.get(`${API}/pacientes/${p.id}/filiacion`, {
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
    });
    expect(check.status()).toBe(200);
    const fili = await check.json();
    expect(fili.telefono_movil).toBe(nuevoTelefono);
    expect((fili.notas ?? '').trim()).toBe(nuevasNotas);
  });

  test('2.9: PUT /pacientes/{id} no permite editar un paciente inexistente', async ({ request }) => {
    const put = await request.put(`${API}/pacientes/99999999`, {
      headers: { 'X-Centro-Id': String(CENTRO_ID) },
      data: { notas: 'x' },
    });
    expect(put.status()).toBe(404);
  });

  test('2.10: el paciente creado aparece en la búsqueda por nombre', async ({ request }) => {
    const p = await PacienteFactory.crear(request);
    pacienteCreadoId = p.id;

    // el buscador indexa por nombre/apellidos/num_historia
    const resp = await request.get(
      `${API}/pacientes/buscar?q=${encodeURIComponent(p.num_historia)}`,
      { headers: { 'X-Centro-Id': String(CENTRO_ID) } }
    );
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.pacientes.some((x: any) => x.id === p.id)).toBe(true);
  });
});
