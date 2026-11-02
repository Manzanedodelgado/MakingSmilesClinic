/**
 * PASO 9 — Bloqueadores Críticos (Serial, Real)
 *
 * Sin mocks. Flujo end-to-end del "camino feliz" completo, en modo serial: cada test
 * depende del anterior. Un solo paciente NUEVO ZZ_E2E para toda la cadena, borrado al final.
 *
 *   crear paciente -> login -> cita -> presupuesto -> aceptar -> acto -> facturar -> persistencia
 *
 * Todos los endpoints verificados en vivo (2026-08-29). Contratos: ver pasos 2, 6, 7, 8.
 * Factura: POST /gestoria/produccion/pacientes/factura  body {paciente_id*, tto_ids*:[int]}  -> 200 {ok, numeroFactura}
 */
import { test, expect } from '@playwright/test';
import { API, CENTRO_ID, COLABORADOR_REAL, TRATAMIENTO_REAL } from './fixtures/constants';
import { PacienteFactory } from './fixtures/factories';
import { borrarPacienteTest, borrarDocumentosTest } from './fixtures/database';

test.describe.configure({ mode: 'serial' });

const H = { 'X-Centro-Id': String(CENTRO_ID) };

test.describe('Paso 9: Bloqueadores Críticos (Serial, Real)', () => {
  let pacienteId: number;
  let presupuestoId: number;
  let lineaId: number;
  let actoId: number;

  test.afterAll(async () => {
    await borrarDocumentosTest();
    if (pacienteId) await borrarPacienteTest(pacienteId);
  });

  test('9.1: BLOQUEADOR — POST /pacientes/nuevo crea el paciente en BD', async ({ request }) => {
    const p = await PacienteFactory.crear(request);
    pacienteId = p.id;
    expect(pacienteId).toBeGreaterThan(0);

    const get = await request.get(`${API}/pacientes/${pacienteId}`, { headers: H });
    expect(get.status()).toBe(200);
    expect((await get.json()).id).toBe(pacienteId);
  });

  test('9.2: BLOQUEADOR — POST /auth/login devuelve un JWT usable', async ({ request }) => {
    const resp = await request.post(`${API}/auth/login`, {
      data: { email: 'test_4134@saas-audit.com', password: 'password123' },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    const token = body.access_token;
    expect(token).toBeTruthy();

    const me = await request.get(`${API}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(me.status()).toBe(200);
  });

  test('9.3: BLOQUEADOR — POST /agenda/citas crea una cita para el paciente', async ({ request }) => {
    const resp = await request.post(`${API}/agenda/citas`, {
      headers: H,
      data: {
        fecha: '2026-09-15',
        hora: '09:30',
        duracion_min: 30,
        paciente_id: pacienteId,
        colaborador_id: COLABORADOR_REAL.id,
        agenda_id: 4,
      },
    });
    expect(resp.status()).toBe(201);
    const citaId = (await resp.json()).id;

    const list = await request.get(`${API}/agenda/citas?fecha=2026-09-15`, { headers: H });
    expect((await list.json()).citas.some((c: any) => c.id === citaId)).toBe(true);
  });

  test('9.4: BLOQUEADOR — POST /pacientes/{id}/presupuestos crea el presupuesto', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/presupuestos`, {
      headers: H,
      data: {
        titulo: 'ZZ_E2E presupuesto bloqueador',
        colaborador_id: COLABORADOR_REAL.id,
        lineas: [
          { tratamiento_id: TRATAMIENTO_REAL.id, pieza: '11', precio: TRATAMIENTO_REAL.precio, cantidad: 1 },
        ],
      },
    });
    expect(resp.status()).toBe(201);
    presupuestoId = (await resp.json()).id;

    const get = await request.get(`${API}/pacientes/${pacienteId}/presupuestos`, { headers: H });
    const presu = (await get.json()).presupuestos.find((p: any) => p.id === presupuestoId);
    expect(presu).toBeTruthy();
    expect(presu.total).toBe(TRATAMIENTO_REAL.precio);
    lineaId = presu.lineas[0].id;
  });

  test('9.5: BLOQUEADOR ★ — POST /presupuestos/{id}/aceptar genera el previsto', async ({ request }) => {
    const resp = await request.post(
      `${API}/pacientes/${pacienteId}/presupuestos/${presupuestoId}/aceptar`,
      { headers: H, data: { lineas_aceptadas: [lineaId] } }
    );
    expect(resp.status()).toBe(200);

    const prev = await request.get(`${API}/pacientes/${pacienteId}/previstos`, { headers: H });
    const previstos = ((await prev.json()).presupuestos ?? []).flatMap((p: any) => p.previstos ?? []);
    expect(previstos.some((t: any) => t.linea_id === lineaId)).toBe(true);
  });

  test('9.6: BLOQUEADOR — POST /pacientes/{id}/actos registra el acto clínico', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/actos`, {
      headers: H,
      data: {
        fecha: '2026-08-29',
        piezas: '11',
        importe: TRATAMIENTO_REAL.precio,
        colaborador_id: COLABORADOR_REAL.id,
        notas: 'ZZ_E2E acto facturable',
      },
    });
    expect(resp.status()).toBe(201);
    actoId = (await resp.json()).id;

    const get = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    expect((await get.json()).actos.some((a: any) => a.id === actoId)).toBe(true);
  });

  test('9.7: BLOQUEADOR ★★ — POST /gestoria/.../factura materializa la factura', async ({ request }) => {
    const resp = await request.post(`${API}/gestoria/produccion/pacientes/factura`, {
      headers: H,
      data: { paciente_id: pacienteId, tto_ids: [actoId] },
    });
    expect(resp.status(), await resp.text()).toBe(200);
    const body = await resp.json();
    expect(body.ok).toBe(true);
    expect(body.numeroFactura).toMatch(/^F\d+$/);

    const trat = await request.get(
      `${API}/gestoria/produccion/pacientes/${pacienteId}/tratamientos`,
      { headers: H }
    );
    const fila = (await trat.json()).data.find((d: any) => String(d.ident) === String(actoId));
    expect(fila.facturado).toBe(true);
    expect(fila.facturaNumero).toBe(body.numeroFactura);
  });

  test('9.8: TODOS los datos de la cadena persisten en BD', async ({ request }) => {
    const pac = await request.get(`${API}/pacientes/${pacienteId}`, { headers: H });
    expect(pac.status()).toBe(200);

    const presu = await request.get(`${API}/pacientes/${pacienteId}/presupuestos`, { headers: H });
    expect((await presu.json()).presupuestos.some((p: any) => p.id === presupuestoId)).toBe(true);

    const actos = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    expect((await actos.json()).actos.some((a: any) => a.id === actoId)).toBe(true);
  });
});
