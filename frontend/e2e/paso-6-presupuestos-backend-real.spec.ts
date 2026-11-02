/**
 * PASO 6 — Presupuestos (Real, Aislado, Estricto)
 *
 * Sin mocks. Ciclo de vida completo del presupuesto contra la API real.
 * Datos: paciente NUEVO ZZ_E2E por test, borrado en afterEach (con sus presupuestos).
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET    /pacientes/{id}/presupuestos                 -> 200 {presupuestos:[{id,titulo,estado,total,lineas:[...]}]}
 *   POST   /pacientes/{id}/presupuestos                 -> 201 {id,num,anuladas_previas}
 *          body {titulo, colaborador_id, lineas:[{tratamiento_id*, pieza, precio, cantidad}]}
 *   PUT    /pacientes/{id}/presupuestos/{pre_id}        -> 200
 *   DELETE /pacientes/{id}/presupuestos/{pre_id}        -> 200 {ok:true}
 *   POST   /pacientes/{id}/presupuestos/{pre_id}/entregar   -> 200
 *   POST   /pacientes/{id}/presupuestos/{pre_id}/aceptar    -> 200 (body {lineas_aceptadas:[linea_id]})  |  400 si vacío
 *   POST   /pacientes/{id}/presupuestos/{pre_id}/duplicar   -> 201 {id,num}
 *
 *   NO existe /presupuestos raíz (todo cuelga de /pacientes/{id}).
 */
import { test, expect, APIRequestContext } from '@playwright/test';
import { API, CENTRO_ID, COLABORADOR_REAL, TRATAMIENTO_REAL } from './fixtures/constants';
import { PacienteFactory } from './fixtures/factories';
import { borrarPacienteTest } from './fixtures/database';

const H = { 'X-Centro-Id': String(CENTRO_ID) };

test.describe('Paso 6: Presupuestos (Real, Aislado, Estricto)', () => {
  let pacienteId: number;

  test.beforeEach(async ({ request }) => {
    pacienteId = (await PacienteFactory.crear(request)).id;
  });

  test.afterEach(async () => {
    if (pacienteId) {
      await borrarPacienteTest(pacienteId);
      pacienteId = 0 as unknown as number;
    }
  });

  interface PresuCreado {
    id: number;
    lineaId: number;
  }

  async function crearPresupuesto(
    request: APIRequestContext,
    lineas: Array<Record<string, unknown>> = [
      { tratamiento_id: TRATAMIENTO_REAL.id, pieza: '11', precio: TRATAMIENTO_REAL.precio, cantidad: 1 },
    ]
  ): Promise<PresuCreado> {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/presupuestos`, {
      headers: H,
      data: { titulo: 'ZZ_E2E presu', colaborador_id: COLABORADOR_REAL.id, lineas },
    });
    expect(resp.status(), await resp.text()).toBe(201);
    const { id } = await resp.json();

    const get = await request.get(`${API}/pacientes/${pacienteId}/presupuestos`, { headers: H });
    const presu = (await get.json()).presupuestos.find((p: any) => p.id === id);
    return { id, lineaId: presu.lineas[0].id };
  }

  test('6.1: GET /presupuestos de paciente nuevo devuelve lista vacía', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}/presupuestos`, { headers: H });
    expect(resp.status()).toBe(200);
    expect((await resp.json()).presupuestos).toHaveLength(0);
  });

  test('6.2: POST /presupuestos crea y calcula el total de las líneas', async ({ request }) => {
    const { id } = await crearPresupuesto(request, [
      { tratamiento_id: TRATAMIENTO_REAL.id, pieza: '11', precio: 30, cantidad: 2 },
    ]);

    const get = await request.get(`${API}/pacientes/${pacienteId}/presupuestos`, { headers: H });
    const presu = (await get.json()).presupuestos.find((p: any) => p.id === id);
    expect(presu.total).toBe(60);
    expect(presu.lineas).toHaveLength(1);
    expect(presu.lineas[0].tratamiento_id).toBe(TRATAMIENTO_REAL.id);
  });

  test('6.3: POST /presupuestos sin líneas con tratamiento_id es rechazado', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/presupuestos`, {
      headers: H,
      data: { titulo: 'ZZ_E2E vacio', colaborador_id: COLABORADOR_REAL.id, lineas: [{ pieza: '11' }] },
    });
    expect(resp.status()).toBe(422);
  });

  test('6.4: PUT /presupuestos/{id} edita el título', async ({ request }) => {
    const { id } = await crearPresupuesto(request);

    const put = await request.put(`${API}/pacientes/${pacienteId}/presupuestos/${id}`, {
      headers: H,
      data: {
        titulo: 'ZZ_E2E editado',
        colaborador_id: COLABORADOR_REAL.id,
        lineas: [{ tratamiento_id: TRATAMIENTO_REAL.id, pieza: '11', precio: 30, cantidad: 1 }],
      },
    });
    expect(put.status()).toBe(200);

    const get = await request.get(`${API}/pacientes/${pacienteId}/presupuestos`, { headers: H });
    const presu = (await get.json()).presupuestos.find((p: any) => p.id === id);
    expect(presu.titulo).toBe('ZZ_E2E editado');
  });

  test('6.5: POST /presupuestos/{id}/entregar responde 200', async ({ request }) => {
    const { id } = await crearPresupuesto(request);
    const resp = await request.post(
      `${API}/pacientes/${pacienteId}/presupuestos/${id}/entregar`,
      { headers: H }
    );
    expect(resp.status()).toBe(200);
  });

  test('6.6: POST /presupuestos/{id}/aceptar sin líneas responde 400', async ({ request }) => {
    const { id } = await crearPresupuesto(request);
    const resp = await request.post(
      `${API}/pacientes/${pacienteId}/presupuestos/${id}/aceptar`,
      { headers: H, data: {} }
    );
    expect(resp.status()).toBe(400);
  });

  test('6.7: POST /presupuestos/{id}/aceptar con la línea genera tratamiento previsto', async ({ request }) => {
    const { id, lineaId } = await crearPresupuesto(request);

    const resp = await request.post(
      `${API}/pacientes/${pacienteId}/presupuestos/${id}/aceptar`,
      { headers: H, data: { lineas_aceptadas: [lineaId] } }
    );
    expect(resp.status()).toBe(200);

    const prev = await request.get(`${API}/pacientes/${pacienteId}/previstos`, { headers: H });
    expect(prev.status()).toBe(200);
    const body = await prev.json();
    // forma real: {presupuestos:[{..., previstos:[{tratamiento_id, linea_id, ...}]}]}
    const previstos = (body.presupuestos ?? []).flatMap((p: any) => p.previstos ?? []);
    expect(previstos.some((t: any) => t.tratamiento_id === TRATAMIENTO_REAL.id)).toBe(true);
    expect(previstos.some((t: any) => t.linea_id === lineaId)).toBe(true);
  });

  test('6.8: POST /presupuestos/{id}/duplicar crea una copia', async ({ request }) => {
    const { id } = await crearPresupuesto(request);

    const dup = await request.post(
      `${API}/pacientes/${pacienteId}/presupuestos/${id}/duplicar`,
      { headers: H }
    );
    expect(dup.status()).toBe(201);
    const copia = await dup.json();
    expect(copia.id).not.toBe(id);

    const get = await request.get(`${API}/pacientes/${pacienteId}/presupuestos`, { headers: H });
    expect((await get.json()).presupuestos.length).toBe(2);
  });

  test('6.9: DELETE /presupuestos/{id} elimina el presupuesto', async ({ request }) => {
    const { id } = await crearPresupuesto(request);

    const del = await request.delete(
      `${API}/pacientes/${pacienteId}/presupuestos/${id}`,
      { headers: H }
    );
    expect(del.status()).toBe(200);
    expect((await del.json()).ok).toBe(true);

    const get = await request.get(`${API}/pacientes/${pacienteId}/presupuestos`, { headers: H });
    expect((await get.json()).presupuestos.find((p: any) => p.id === id)).toBeFalsy();
  });
});
