/**
 * PASO 7 — Consulta Clínica / 3 Caminos (Real, Aislado, Estricto)
 *
 * Sin mocks. Flujo de consulta (Escucha Activa → SOAP → análisis → receta →
 * recomendaciones → cierre) contra la API real.
 * Datos: paciente NUEVO ZZ_E2E por test, borrado en afterEach.
 * El usuario de test es colaborador (lo garantiza global.setup) — necesario para /cerrar.
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET  /pacientes/{id}/consulta/camino          -> 200 {camino, es_nuevo, anamnesis_completa, cita_confirmada, tiene_previstos}
 *   POST /pacientes/{id}/consulta/escucha         -> 200 {soap, presupuesto, receta, mensaje}   body {texto*}
 *   POST /pacientes/{id}/consulta/soap            -> 201 {ok, soap_id, cita_id}   body {subjetivo, objetivo, analisis, plan}
 *   POST /pacientes/{id}/consulta/analizar        -> 200 {pieza, nueva:{pregunta,...}}   body {evidencia*}
 *   POST /pacientes/{id}/consulta/receta          -> 201 {ok, receta_id, n}   body {medicamentos:[{medicamento*}], diagnostico}
 *   POST /pacientes/{id}/consulta/recomendaciones -> 201 {ok, recomendacion_id, items_count}   body {items:[string]}
 *   POST /pacientes/{id}/consulta/cerrar          -> 201 {registrados:[...], n}   body {nota, tratamientos:[{texto*, pieza, precio}]}
 *
 *   (prefijo real /pacientes/{id}/consulta/...  — NO existe GET/PUT/DELETE /consulta/{id})
 */
import { test, expect } from '@playwright/test';
import { API, CENTRO_ID } from './fixtures/constants';
import { PacienteFactory } from './fixtures/factories';
import { borrarPacienteTest } from './fixtures/database';

const H = { 'X-Centro-Id': String(CENTRO_ID) };

test.describe('Paso 7: Consulta Clínica (Real, Aislado, Estricto)', () => {
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

  test('7.1: GET /consulta/camino detecta el camino para un paciente nuevo', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}/consulta/camino`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.es_nuevo).toBe(true);
    expect([1, 2, 3]).toContain(body.camino);
    expect(body.tiene_previstos).toBe(false);
  });

  test('7.2: POST /consulta/escucha devuelve SOAP estructurado y mensaje', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/consulta/escucha`, {
      headers: H,
      data: { texto: 'El paciente refiere dolor en el molar superior derecho al masticar' },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.soap).toBeTruthy();
    expect(typeof body.soap.subjetivo).toBe('string');
    expect(body.soap.subjetivo.length).toBeGreaterThan(0);
  });

  test('7.3: POST /consulta/escucha sin texto es rechazado (422)', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/consulta/escucha`, {
      headers: H,
      data: {},
    });
    expect(resp.status()).toBe(422);
  });

  test('7.4: POST /consulta/soap crea la nota y la cita del día', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/consulta/soap`, {
      headers: H,
      data: { subjetivo: 'Dolor', objetivo: 'Caries en 16', analisis: 'Pulpitis irreversible', plan: 'Endodoncia' },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    expect(body.ok).toBe(true);
    expect(body.soap_id).toBeGreaterThan(0);
    expect(body.cita_id).toBeGreaterThan(0);
  });

  test('7.5: POST /consulta/soap dos veces actualiza el mismo SOAP (no duplica)', async ({ request }) => {
    const r1 = await request.post(`${API}/pacientes/${pacienteId}/consulta/soap`, {
      headers: H,
      data: { subjetivo: 'v1' },
    });
    const r2 = await request.post(`${API}/pacientes/${pacienteId}/consulta/soap`, {
      headers: H,
      data: { subjetivo: 'v2' },
    });
    expect((await r1.json()).soap_id).toBe((await r2.json()).soap_id);
  });

  test('7.6: POST /consulta/analizar propone una incógnita a partir de la evidencia', async ({ request }) => {
    await request.post(`${API}/pacientes/${pacienteId}/consulta/escucha`, {
      headers: H,
      data: { texto: 'dolor en 16 con caries visible' },
    });
    const resp = await request.post(`${API}/pacientes/${pacienteId}/consulta/analizar`, {
      headers: H,
      data: { evidencia: 'Dolor en 16 con caries visible en cara oclusal' },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body).toHaveProperty('nueva');
    expect(typeof body.nueva.pregunta).toBe('string');
  });

  test('7.7: POST /consulta/analizar sin evidencia es rechazado (422)', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/consulta/analizar`, {
      headers: H,
      data: {},
    });
    expect(resp.status()).toBe(422);
  });

  test('7.8: POST /consulta/receta crea la receta y aparece en /recetas', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/consulta/receta`, {
      headers: H,
      data: {
        medicamentos: [{ medicamento: 'ZZ_E2E Amoxicilina 750', posologia: '1 comp/8h' }],
        diagnostico: 'Absceso periapical',
      },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    expect(body.ok).toBe(true);
    expect(body.receta_id).toBeGreaterThan(0);

    const get = await request.get(`${API}/pacientes/${pacienteId}/recetas`, { headers: H });
    const recetas = (await get.json()).recetas;
    expect(recetas.some((r: any) => r.medicamento?.includes('ZZ_E2E Amoxicilina'))).toBe(true);
  });

  test('7.9: POST /consulta/recomendaciones guarda los ítems seleccionados', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/consulta/recomendaciones`, {
      headers: H,
      data: { items: ['Cepillado 3 veces al día', 'Uso de hilo dental', 'Enjuague con flúor'] },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    expect(body.ok).toBe(true);
    expect(body.items_count).toBe(3);
  });

  test('7.10: POST /consulta/cerrar registra un acto por cada tratamiento decidido', async ({ request }) => {
    await request.post(`${API}/pacientes/${pacienteId}/consulta/escucha`, {
      headers: H,
      data: { texto: 'dolor en 16' },
    });

    const resp = await request.post(`${API}/pacientes/${pacienteId}/consulta/cerrar`, {
      headers: H,
      data: {
        nota: 'ZZ_E2E cierre de consulta',
        tratamientos: [{ texto: 'Limpieza', pieza: '11', precio: 30 }],
      },
    });
    expect(resp.status()).toBe(201);
    expect((await resp.json()).n).toBe(1);

    const actos = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    expect((await actos.json()).actos.length).toBeGreaterThan(0);
  });

  test('7.11: Flujo completo Camino 2: escucha -> soap -> receta -> recomendaciones -> cierre', async ({ request }) => {
    const escucha = await request.post(`${API}/pacientes/${pacienteId}/consulta/escucha`, {
      headers: H,
      data: { texto: 'Paciente con gingivitis generalizada y sangrado al cepillado' },
    });
    expect(escucha.status()).toBe(200);

    const soap = await request.post(`${API}/pacientes/${pacienteId}/consulta/soap`, {
      headers: H,
      data: { subjetivo: 'Sangrado', objetivo: 'Gingivitis', analisis: 'Gingivitis', plan: 'Tartrectomía + higiene' },
    });
    expect(soap.status()).toBe(201);

    const receta = await request.post(`${API}/pacientes/${pacienteId}/consulta/receta`, {
      headers: H,
      data: { medicamentos: [{ medicamento: 'Clorhexidina 0.12%', posologia: 'enjuague 2/día' }] },
    });
    expect(receta.status()).toBe(201);

    const reco = await request.post(`${API}/pacientes/${pacienteId}/consulta/recomendaciones`, {
      headers: H,
      data: { items: ['Técnica de cepillado de Bass', 'Cepillo suave'] },
    });
    expect(reco.status()).toBe(201);

    const cierre = await request.post(`${API}/pacientes/${pacienteId}/consulta/cerrar`, {
      headers: H,
      data: { nota: 'ZZ_E2E flujo completo', tratamientos: [{ texto: 'Tartrectomía', precio: 45 }] },
    });
    expect(cierre.status()).toBe(201);
    expect((await cierre.json()).n).toBe(1);
  });
});
