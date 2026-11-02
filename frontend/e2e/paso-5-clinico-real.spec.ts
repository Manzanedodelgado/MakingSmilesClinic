/**
 * PASO 5 — Historia Clínica (Real, Aislado, Estricto)
 *
 * Sin mocks. Endpoints clínicos del paciente contra la API real.
 * Datos: paciente NUEVO ZZ_E2E por test, borrado en afterEach.
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET  /pacientes/{id}/recetas        -> 200 {recetas:[]}
 *   GET  /pacientes/{id}/previstos      -> 200 {presupuestos:[]}
 *   GET  /pacientes/{id}/alertas        -> 200 {alertas:[], medicaciones:[], notas}
 *   POST /pacientes/{id}/alertas        -> 201 {id}          body {texto*, severidad}
 *   PUT  /pacientes/{id}/alertas/{aid}  -> 200               body {activo, texto, severidad}
 *   GET  /pacientes/{id}/cascabel       -> 200 {scorePorcentaje, citasAsistidas, citasNoShow, ...}
 *   POST /pacientes/{id}/medicaciones   -> 201 {id}          body {farmaco*, dosis, frecuencia, pauta}
 *   GET  /pacientes/{id}/plan-proxima   -> 200 {plan:null | {id,minutos,nota,items,estado}}
 *   PUT  /pacientes/{id}/plan-proxima   -> 200 {id}          body {minutos, nota, items:[{tratamiento*, minutos}]}
 *   DELETE /pacientes/{id}/plan-proxima -> 204
 *
 *   (prefijo real es /pacientes/{id}/..., NO /clinico/{id}/...)
 */
import { test, expect } from '@playwright/test';
import { API, CENTRO_ID } from './fixtures/constants';
import { PacienteFactory } from './fixtures/factories';
import { borrarPacienteTest } from './fixtures/database';

const H = { 'X-Centro-Id': String(CENTRO_ID) };

test.describe('Paso 5: Historia Clínica (Real, Aislado, Estricto)', () => {
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

  test('5.1: GET /recetas de paciente nuevo devuelve lista vacía', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}/recetas`, { headers: H });
    expect(resp.status()).toBe(200);
    expect((await resp.json()).recetas).toEqual([]);
  });

  test('5.2: GET /previstos de paciente nuevo no tiene presupuestos', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}/previstos`, { headers: H });
    expect(resp.status()).toBe(200);
    expect((await resp.json()).presupuestos).toEqual([]);
  });

  test('5.3: GET /alertas de paciente nuevo devuelve estructura vacía', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}/alertas`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.alertas).toEqual([]);
    expect(body.medicaciones).toEqual([]);
  });

  test('5.4: POST /alertas crea alerta y aparece en el GET', async ({ request }) => {
    const post = await request.post(`${API}/pacientes/${pacienteId}/alertas`, {
      headers: H,
      data: { texto: 'ZZ_E2E alergia a penicilina', severidad: 'alta' },
    });
    expect(post.status()).toBe(201);
    const alertaId = (await post.json()).id;

    const get = await request.get(`${API}/pacientes/${pacienteId}/alertas`, { headers: H });
    const alerta = (await get.json()).alertas.find((a: any) => a.id === alertaId);
    expect(alerta).toBeTruthy();
    expect(alerta.texto).toBe('ZZ_E2E alergia a penicilina');
  });

  test('5.5: POST /alertas sin texto es rechazado (422)', async ({ request }) => {
    const post = await request.post(`${API}/pacientes/${pacienteId}/alertas`, {
      headers: H,
      data: { severidad: 'alta' },
    });
    expect(post.status()).toBe(422);
  });

  test('5.6: PUT /alertas/{id} desactiva la alerta', async ({ request }) => {
    const post = await request.post(`${API}/pacientes/${pacienteId}/alertas`, {
      headers: H,
      data: { texto: 'ZZ_E2E alerta temporal' },
    });
    const alertaId = (await post.json()).id;

    const put = await request.put(`${API}/pacientes/${pacienteId}/alertas/${alertaId}`, {
      headers: H,
      data: { activo: false },
    });
    expect(put.status()).toBe(200);
    expect((await put.json()).activo).toBe(false);

    const get = await request.get(`${API}/pacientes/${pacienteId}/alertas`, { headers: H });
    const alerta = (await get.json()).alertas.find((a: any) => a.id === alertaId);
    expect(alerta).toBeTruthy();
    expect(alerta.activo).toBe(false);
  });

  test('5.7: GET /cascabel devuelve el resumen de asistencia', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}/cascabel`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('citasTotal');
    expect(body.citasTotal).toBe(0);
    expect(body.citasNoShow).toBe(0);
  });

  test('5.8: POST /medicaciones agrega medicación y aparece en /alertas', async ({ request }) => {
    const post = await request.post(`${API}/pacientes/${pacienteId}/medicaciones`, {
      headers: H,
      data: { farmaco: 'ZZ_E2E Ibuprofeno 600', dosis: '1 comp', frecuencia: 'cada 8h' },
    });
    expect(post.status()).toBe(201);

    const get = await request.get(`${API}/pacientes/${pacienteId}/alertas`, { headers: H });
    const meds = (await get.json()).medicaciones;
    expect(meds.some((m: any) => (m.farmaco ?? m.nombre ?? '').includes('ZZ_E2E Ibuprofeno'))).toBe(true);
  });

  test('5.9: POST /medicaciones sin farmaco es rechazado (422)', async ({ request }) => {
    const post = await request.post(`${API}/pacientes/${pacienteId}/medicaciones`, {
      headers: H,
      data: { dosis: '1 comp' },
    });
    expect(post.status()).toBe(422);
  });

  test('5.10: GET /plan-proxima de paciente nuevo devuelve plan null', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}/plan-proxima`, { headers: H });
    expect(resp.status()).toBe(200);
    expect((await resp.json()).plan).toBeNull();
  });

  test('5.11: PUT /plan-proxima crea el plan y persiste', async ({ request }) => {
    const put = await request.put(`${API}/pacientes/${pacienteId}/plan-proxima`, {
      headers: H,
      data: { minutos: 30, nota: 'ZZ_E2E revisión', items: [{ tratamiento: 'Revisión', minutos: 30 }] },
    });
    expect(put.status()).toBe(200);

    const get = await request.get(`${API}/pacientes/${pacienteId}/plan-proxima`, { headers: H });
    const plan = (await get.json()).plan;
    expect(plan).toBeTruthy();
    expect(plan.minutos).toBe(30);
    expect(plan.nota).toBe('ZZ_E2E revisión');
    expect(plan.items).toHaveLength(1);
    expect(plan.items[0].tratamiento).toBe('Revisión');
  });

  test('5.12: DELETE /plan-proxima elimina el plan', async ({ request }) => {
    await request.put(`${API}/pacientes/${pacienteId}/plan-proxima`, {
      headers: H,
      data: { minutos: 15, items: [{ tratamiento: 'Control', minutos: 15 }] },
    });

    const del = await request.delete(`${API}/pacientes/${pacienteId}/plan-proxima`, { headers: H });
    expect(del.status()).toBe(204);

    const get = await request.get(`${API}/pacientes/${pacienteId}/plan-proxima`, { headers: H });
    expect((await get.json()).plan).toBeNull();
  });
});
