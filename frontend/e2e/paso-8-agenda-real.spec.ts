/**
 * PASO 8 — Agenda (Real, Aislado, Estricto)
 *
 * Sin mocks. Ciclo de vida de la cita contra la API real.
 * Datos: paciente NUEVO ZZ_E2E por test; sus citas se borran al borrar el paciente.
 *        agenda_id 4 y colaborador_id 4 son reales del centro 1.
 *
 * Contrato real verificado en /openapi.json + pruebas en vivo (2026-08-29):
 *   GET /agenda/referencias                 -> 200 {agendas, gabinetes, estados, tipos_cita, colaboradores, ...}
 *   GET /agenda/huecos?dias=N               -> 200
 *   GET /agenda/citas?fecha=YYYY-MM-DD      -> 200 {citas:[{id,fecha,hora,duracion_min,colaborador_id,estado_id,estado_nombre,paciente_id,nombre,apellidos,num_historia,...}]}
 *   POST /agenda/citas                      -> 201 {id}   body {fecha*, hora*, duracion_min, paciente_id, colaborador_id, agenda_id}
 *   PUT  /agenda/citas/{id}                 -> 200 {id}   body = CitaIn completo
 *   PUT  /agenda/citas/{id}/mover           -> 200 {id}   body {fecha*, hora*, gabinete_id}
 *   PUT  /agenda/citas/{id}/estado          -> 200 {id,estado_id}   body {estado_id*}
 *   PUT  /agenda/citas/{id}/anular          -> 200 {id}
 *
 *   (anular y estado son PUT, no POST. NO existe GET individual ni DELETE de cita.)
 */
import { test, expect, APIRequestContext } from '@playwright/test';
import { API, CENTRO_ID, COLABORADOR_REAL } from './fixtures/constants';
import { PacienteFactory } from './fixtures/factories';
import { borrarPacienteTest } from './fixtures/database';

const H = { 'X-Centro-Id': String(CENTRO_ID) };
const AGENDA_ID = 4;
const FECHA = '2026-09-15';

test.describe('Paso 8: Agenda (Real, Aislado, Estricto)', () => {
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

  async function crearCita(
    request: APIRequestContext,
    extra: Record<string, unknown> = {}
  ): Promise<number> {
    const resp = await request.post(`${API}/agenda/citas`, {
      headers: H,
      data: {
        fecha: FECHA,
        hora: '10:00',
        duracion_min: 30,
        paciente_id: pacienteId,
        colaborador_id: COLABORADOR_REAL.id,
        agenda_id: AGENDA_ID,
        ...extra,
      },
    });
    expect(resp.status(), await resp.text()).toBe(201);
    return (await resp.json()).id;
  }

  async function getCita(request: APIRequestContext, citaId: number, fecha = FECHA) {
    const resp = await request.get(`${API}/agenda/citas?fecha=${fecha}`, { headers: H });
    expect(resp.status()).toBe(200);
    return (await resp.json()).citas.find((c: any) => c.id === citaId);
  }

  test('8.1: GET /agenda/referencias trae agendas, estados y colaboradores del centro', async ({ request }) => {
    const resp = await request.get(`${API}/agenda/referencias`, { headers: H });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body.agendas)).toBe(true);
    expect(Array.isArray(body.estados)).toBe(true);
    expect(body.colaboradores.some((c: any) => c.id === COLABORADOR_REAL.id)).toBe(true);
  });

  test('8.2: GET /agenda/huecos responde con disponibilidad', async ({ request }) => {
    const resp = await request.get(`${API}/agenda/huecos?dias=7`, { headers: H });
    expect(resp.status()).toBe(200);
  });

  test('8.3: POST /agenda/citas crea la cita para el paciente', async ({ request }) => {
    const citaId = await crearCita(request);
    const cita = await getCita(request, citaId);
    expect(cita).toBeTruthy();
    expect(cita.paciente_id).toBe(pacienteId);
    expect(cita.hora).toBe('10:00');
    expect(cita.duracion_min).toBe(30);
    expect(cita.colaborador_id).toBe(COLABORADOR_REAL.id);
  });

  test('8.4: POST /agenda/citas sin fecha ni hora es rechazado (422)', async ({ request }) => {
    const resp = await request.post(`${API}/agenda/citas`, {
      headers: H,
      data: { paciente_id: pacienteId, colaborador_id: COLABORADOR_REAL.id, agenda_id: AGENDA_ID },
    });
    expect(resp.status()).toBe(422);
  });

  test('8.5: GET /agenda/citas?fecha= filtra por día', async ({ request }) => {
    const citaId = await crearCita(request);
    const resp = await request.get(`${API}/agenda/citas?fecha=${FECHA}`, { headers: H });
    const body = await resp.json();
    expect(body.citas.every((c: any) => c.fecha === FECHA)).toBe(true);
    expect(body.citas.some((c: any) => c.id === citaId)).toBe(true);
  });

  test('8.6: PUT /agenda/citas/{id}/mover cambia fecha y hora', async ({ request }) => {
    const citaId = await crearCita(request);

    const mov = await request.put(`${API}/agenda/citas/${citaId}/mover`, {
      headers: H,
      data: { fecha: '2026-09-16', hora: '12:30' },
    });
    expect(mov.status()).toBe(200);

    const cita = await getCita(request, citaId, '2026-09-16');
    expect(cita).toBeTruthy();
    expect(cita.hora).toBe('12:30');
  });

  test('8.7: PUT /agenda/citas/{id}/mover sin fecha ni hora es rechazado (422)', async ({ request }) => {
    const citaId = await crearCita(request);
    const resp = await request.put(`${API}/agenda/citas/${citaId}/mover`, { headers: H, data: {} });
    expect(resp.status()).toBe(422);
  });

  test('8.8: PUT /agenda/citas/{id}/estado cambia el estado', async ({ request }) => {
    const citaId = await crearCita(request);

    const refs = await (await request.get(`${API}/agenda/referencias`, { headers: H })).json();
    const nuevoEstado = refs.estados.find((e: any) => e.id !== 0)?.id ?? 1;

    const put = await request.put(`${API}/agenda/citas/${citaId}/estado`, {
      headers: H,
      data: { estado_id: nuevoEstado },
    });
    expect(put.status()).toBe(200);
    expect((await put.json()).estado_id).toBe(nuevoEstado);

    const cita = await getCita(request, citaId);
    expect(cita.estado_id).toBe(nuevoEstado);
  });

  test('8.9: PUT /agenda/citas/{id}/estado sin estado_id es rechazado (422)', async ({ request }) => {
    const citaId = await crearCita(request);
    const resp = await request.put(`${API}/agenda/citas/${citaId}/estado`, { headers: H, data: {} });
    expect(resp.status()).toBe(422);
  });

  test('8.10: PUT /agenda/citas/{id}/anular quita la cita de la agenda del día', async ({ request }) => {
    const citaId = await crearCita(request);

    const anul = await request.put(`${API}/agenda/citas/${citaId}/anular`, { headers: H });
    expect(anul.status()).toBe(200);

    // por defecto GET /agenda/citas no incluye anuladas
    const resp = await request.get(`${API}/agenda/citas?fecha=${FECHA}`, { headers: H });
    expect((await resp.json()).citas.some((c: any) => c.id === citaId)).toBe(false);

    // con incluir_anuladas sí aparece
    const conAnuladas = await request.get(
      `${API}/agenda/citas?fecha=${FECHA}&incluir_anuladas=true`,
      { headers: H }
    );
    expect((await conAnuladas.json()).citas.some((c: any) => c.id === citaId)).toBe(true);
  });

  test('8.11: PUT /agenda/citas/{id} edita duración y notas', async ({ request }) => {
    const citaId = await crearCita(request);

    const put = await request.put(`${API}/agenda/citas/${citaId}`, {
      headers: H,
      data: {
        fecha: FECHA,
        hora: '10:00',
        duracion_min: 60,
        paciente_id: pacienteId,
        colaborador_id: COLABORADOR_REAL.id,
        agenda_id: AGENDA_ID,
        notas: 'ZZ_E2E cita editada',
      },
    });
    expect(put.status()).toBe(200);

    const cita = await getCita(request, citaId);
    expect(cita.duracion_min).toBe(60);
    expect(cita.notas).toBe('ZZ_E2E cita editada');
  });
});
