/**
 * PASO 3 — Actos Clínicos (Real, Aislado, Estricto)
 *
 * Sin mocks. CRUD de actos contra la API real.
 * Datos:
 *   - todos los actos se crean sobre un paciente NUEVO ZZ_E2E, borrado en afterEach.
 *   - el doctor es COLABORADOR_REAL (obligatorio: la API rechaza el acto sin colaborador_id).
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET    /pacientes/{id}/actos            -> 200 {actos:[{id,fecha,piezas,doctor,tratamiento,importe,estado,facturado}], indicadores}
 *   POST   /pacientes/{id}/actos            -> 201 {id}   body {fecha*, piezas, importe, notas, colaborador_id*}
 *   PUT    /pacientes/{id}/actos/{acto_id}  -> 200 {id}   (notas -> campo "tratamiento" en el GET)
 *   DELETE /pacientes/{id}/actos/{acto_id}  -> 200 {ok:true}
 */
import { test, expect } from '@playwright/test';
import { API, CENTRO_ID, COLABORADOR_REAL } from './fixtures/constants';
import { PacienteFactory } from './fixtures/factories';
import { borrarPacienteTest } from './fixtures/database';

const H = { 'X-Centro-Id': String(CENTRO_ID) };

test.describe('Paso 3: Actos Clínicos (Real, Aislado, Estricto)', () => {
  let pacienteId: number;

  test.beforeEach(async ({ request }) => {
    const p = await PacienteFactory.crear(request);
    pacienteId = p.id;
  });

  test.afterEach(async () => {
    if (pacienteId) {
      await borrarPacienteTest(pacienteId);
      pacienteId = 0 as unknown as number;
    }
  });

  async function crearActo(
    request: import('@playwright/test').APIRequestContext,
    extra: Record<string, unknown> = {}
  ): Promise<number> {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/actos`, {
      headers: H,
      data: {
        fecha: '2026-08-29',
        piezas: '11',
        importe: 50,
        notas: 'ZZ_E2E acto',
        colaborador_id: COLABORADOR_REAL.id,
        ...extra,
      },
    });
    expect(resp.status(), await resp.text()).toBe(201);
    return (await resp.json()).id;
  }

  test('3.1: GET /actos de un paciente nuevo devuelve lista vacía', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body.actos)).toBe(true);
    expect(body.actos).toHaveLength(0);
  });

  test('3.2: POST /actos sin colaborador_id es rechazado (422)', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/actos`, {
      headers: H,
      data: { fecha: '2026-08-29', piezas: '11', importe: 50 },
    });
    expect(resp.status()).toBe(422);
  });

  test('3.3: POST /actos sin fecha es rechazado (422)', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/actos`, {
      headers: H,
      data: { piezas: '11', colaborador_id: COLABORADOR_REAL.id },
    });
    expect(resp.status()).toBe(422);
  });

  test('3.4: POST /actos válido persiste y aparece en el GET', async ({ request }) => {
    const actoId = await crearActo(request, { piezas: '16', importe: 75, notas: 'ZZ_E2E endodoncia' });

    const resp = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    const body = await resp.json();
    const acto = body.actos.find((a: any) => a.id === actoId);
    expect(acto).toBeTruthy();
    expect(acto.piezas).toBe('16');
    expect(acto.importe).toBe(75);
    expect(acto.doctor).toBe(COLABORADOR_REAL.nombre);
    expect(acto.tratamiento).toBe('ZZ_E2E endodoncia');
    expect(acto.estado).toBe('Realizado');
  });

  test('3.5: PUT /actos/{id} edita y persiste', async ({ request }) => {
    const actoId = await crearActo(request);

    const put = await request.put(`${API}/pacientes/${pacienteId}/actos/${actoId}`, {
      headers: H,
      data: { notas: 'ZZ_E2E editado', importe: 120 },
    });
    expect(put.status()).toBe(200);

    const resp = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    const acto = (await resp.json()).actos.find((a: any) => a.id === actoId);
    expect(acto.tratamiento).toBe('ZZ_E2E editado');
    expect(acto.importe).toBe(120);
  });

  test('3.6: DELETE /actos/{id} elimina el acto', async ({ request }) => {
    const actoId = await crearActo(request);

    const del = await request.delete(`${API}/pacientes/${pacienteId}/actos/${actoId}`, { headers: H });
    expect(del.status()).toBe(200);
    expect((await del.json()).ok).toBe(true);

    const resp = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    const body = await resp.json();
    expect(body.actos.find((a: any) => a.id === actoId)).toBeFalsy();
  });

  test('3.7: crear 3 actos y el indicador "ultima_visita" refleja la fecha', async ({ request }) => {
    await crearActo(request, { fecha: '2026-08-01' });
    await crearActo(request, { fecha: '2026-08-15' });
    await crearActo(request, { fecha: '2026-08-29' });

    const resp = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    const body = await resp.json();
    expect(body.actos).toHaveLength(3);
    expect(body.indicadores.ultima_visita).toBe('2026-08-29');
  });

  test('3.8: DELETE de un acto inexistente responde 404', async ({ request }) => {
    const del = await request.delete(`${API}/pacientes/${pacienteId}/actos/99999999`, { headers: H });
    expect(del.status()).toBe(404);
  });
});
