/**
 * PASO 15 — Integración E2E completa (Real, Aislado, Estricto)
 *
 * Sin mocks. Compone los flujos ya verificados uno a uno en los pasos 2–14 en un
 * recorrido serial coherente del ciclo de vida completo de un paciente:
 *
 *   crear paciente -> agenda -> radiología -> consulta (escucha/SOAP/receta/recomend.)
 *   -> presupuesto -> aceptar -> acto -> facturar -> informes -> consistencia -> borrado
 *
 * Un único paciente NUEVO ZZ_E2E para toda la cadena, borrado en afterAll junto con
 * sus documentos administrativos.
 *
 * Todos los contratos verificados en vivo (2026-08-29) — ver pasos 2, 6, 7, 8, 9, 10, 14.
 */
import fs from 'fs';
import path from 'path';
import { test, expect } from '@playwright/test';
import {
  API,
  CENTRO_ID,
  COLABORADOR_REAL,
  TRATAMIENTO_REAL,
} from './fixtures/constants';
import { PacienteFactory } from './fixtures/factories';
import { borrarPacienteTest, borrarDocumentosTest } from './fixtures/database';

test.describe.configure({ mode: 'serial' });

const H = { 'X-Centro-Id': String(CENTRO_ID) };
const RX_IMG = path.join(__dirname, 'fixtures', 'rx-test.png');

test.describe('Paso 15: Integración E2E completa (Real, Aislado, Estricto)', () => {
  let pacienteId: number;
  let citaId: number;
  let imagenId: number;
  let presupuestoId: number;
  let lineaId: number;
  let actoId: number;
  let facturaNumero: string;

  test.afterAll(async () => {
    await borrarDocumentosTest();
    if (pacienteId) await borrarPacienteTest(pacienteId);
  });

  test('15.1: alta del paciente y persistencia', async ({ request }) => {
    pacienteId = (await PacienteFactory.crear(request)).id;
    const get = await request.get(`${API}/pacientes/${pacienteId}`, { headers: H });
    expect(get.status()).toBe(200);
    expect((await get.json()).id).toBe(pacienteId);
  });

  test('15.2: se le agenda una cita', async ({ request }) => {
    const resp = await request.post(`${API}/agenda/citas`, {
      headers: H,
      data: {
        fecha: '2026-09-10',
        hora: '09:00',
        duracion_min: 45,
        paciente_id: pacienteId,
        colaborador_id: COLABORADOR_REAL.id,
        agenda_id: 4,
      },
    });
    expect(resp.status()).toBe(201);
    citaId = (await resp.json()).id;

    const list = await request.get(`${API}/agenda/citas?fecha=2026-09-10`, { headers: H });
    expect((await list.json()).citas.some((c: any) => c.id === citaId)).toBe(true);
  });

  test('15.3: se le sube una radiografía y se le añade un hallazgo', async ({ request }) => {
    const up = await request.post(`${API}/pacientes/${pacienteId}/radiologia`, {
      headers: H,
      multipart: {
        file: { name: 'rx-test.png', mimeType: 'image/png', buffer: fs.readFileSync(RX_IMG) },
      },
    });
    expect(up.status()).toBe(201);
    imagenId = (await up.json()).id;

    const hall = await request.post(`${API}/radiologia/${imagenId}/hallazgos`, {
      headers: H,
      data: { descripcion: 'ZZ_E2E caries en 16', pieza: '16', confianza: 0.9 },
    });
    expect(hall.status()).toBe(201);
  });

  test('15.4: consulta — escucha, SOAP, receta y recomendaciones', async ({ request }) => {
    const escucha = await request.post(`${API}/pacientes/${pacienteId}/consulta/escucha`, {
      headers: H,
      data: { texto: 'Dolor agudo en 16, caries visible confirmada por RX' },
    });
    expect(escucha.status()).toBe(200);

    const soap = await request.post(`${API}/pacientes/${pacienteId}/consulta/soap`, {
      headers: H,
      data: { subjetivo: 'Dolor', objetivo: 'Caries 16', analisis: 'Pulpitis', plan: 'Endodoncia + corona' },
    });
    expect(soap.status()).toBe(201);

    const receta = await request.post(`${API}/pacientes/${pacienteId}/consulta/receta`, {
      headers: H,
      data: { medicamentos: [{ medicamento: 'Ibuprofeno 600', posologia: '1/8h' }] },
    });
    expect(receta.status()).toBe(201);

    const reco = await request.post(`${API}/pacientes/${pacienteId}/consulta/recomendaciones`, {
      headers: H,
      data: { items: ['Evitar masticar por el lado derecho', 'Analgesia si dolor'] },
    });
    expect(reco.status()).toBe(201);
  });

  test('15.5: presupuesto con el tratamiento del plan', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/presupuestos`, {
      headers: H,
      data: {
        titulo: 'ZZ_E2E plan de tratamiento',
        colaborador_id: COLABORADOR_REAL.id,
        lineas: [
          { tratamiento_id: TRATAMIENTO_REAL.id, pieza: '16', precio: TRATAMIENTO_REAL.precio, cantidad: 1 },
        ],
      },
    });
    expect(resp.status()).toBe(201);
    presupuestoId = (await resp.json()).id;

    const get = await request.get(`${API}/pacientes/${pacienteId}/presupuestos`, { headers: H });
    const presu = (await get.json()).presupuestos.find((p: any) => p.id === presupuestoId);
    expect(presu.total).toBe(TRATAMIENTO_REAL.precio);
    lineaId = presu.lineas[0].id;
  });

  test('15.6: entregar y aceptar el presupuesto genera el previsto', async ({ request }) => {
    const entregar = await request.post(
      `${API}/pacientes/${pacienteId}/presupuestos/${presupuestoId}/entregar`,
      { headers: H }
    );
    expect(entregar.status()).toBe(200);

    const aceptar = await request.post(
      `${API}/pacientes/${pacienteId}/presupuestos/${presupuestoId}/aceptar`,
      { headers: H, data: { lineas_aceptadas: [lineaId] } }
    );
    expect(aceptar.status()).toBe(200);

    const prev = await request.get(`${API}/pacientes/${pacienteId}/previstos`, { headers: H });
    const previstos = ((await prev.json()).presupuestos ?? []).flatMap((p: any) => p.previstos ?? []);
    expect(previstos.some((t: any) => t.linea_id === lineaId)).toBe(true);
  });

  test('15.7: se registra el acto clínico realizado', async ({ request }) => {
    const resp = await request.post(`${API}/pacientes/${pacienteId}/actos`, {
      headers: H,
      data: {
        fecha: '2026-08-29',
        piezas: '16',
        importe: TRATAMIENTO_REAL.precio,
        colaborador_id: COLABORADOR_REAL.id,
        notas: 'ZZ_E2E tratamiento realizado',
      },
    });
    expect(resp.status()).toBe(201);
    actoId = (await resp.json()).id;

    const get = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    expect((await get.json()).actos.some((a: any) => a.id === actoId)).toBe(true);
  });

  test('15.8: se factura el acto', async ({ request }) => {
    const resp = await request.post(`${API}/gestoria/produccion/pacientes/factura`, {
      headers: H,
      data: { paciente_id: pacienteId, tto_ids: [actoId] },
    });
    expect(resp.status(), await resp.text()).toBe(200);
    facturaNumero = (await resp.json()).numeroFactura;
    expect(facturaNumero).toMatch(/^F\d+$/);

    const trat = await request.get(
      `${API}/gestoria/produccion/pacientes/${pacienteId}/tratamientos`,
      { headers: H }
    );
    const fila = (await trat.json()).data.find((d: any) => String(d.ident) === String(actoId));
    expect(fila.facturado).toBe(true);
    expect(fila.facturaNumero).toBe(facturaNumero);
  });

  test('15.9: el paciente aparece en un informe filtrado por apellido', async ({ request }) => {
    const resp = await request.post(`${API}/informes/ejecutar`, {
      headers: H,
      data: {
        entidad: 'pacientes',
        columnas: ['nombre', 'apellidos'],
        filtros: [{ campo: 'apellidos', op: 'contiene', valor: 'ZZ_E2E' }],
        limite: 50,
      },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.total).toBeGreaterThan(0);
    expect(body.filas.some((f: any) => String(f.apellidos).includes('ZZ_E2E'))).toBe(true);
  });

  test('15.10: integridad — un presupuesto ACEPTADO no se puede borrar (409)', async ({ request }) => {
    // el backend protege los previstos generados: DELETE y anular se rechazan con 409
    const del = await request.delete(
      `${API}/pacientes/${pacienteId}/presupuestos/${presupuestoId}`,
      { headers: H }
    );
    expect(del.status()).toBe(409);

    const anular = await request.post(
      `${API}/pacientes/${pacienteId}/presupuestos/${presupuestoId}/anular`,
      { headers: H }
    );
    expect(anular.status()).toBe(409);

    // el acto y la factura siguen intactos
    const actos = await request.get(`${API}/pacientes/${pacienteId}/actos`, { headers: H });
    expect((await actos.json()).actos.some((a: any) => a.id === actoId)).toBe(true);

    const trat = await request.get(
      `${API}/gestoria/produccion/pacientes/${pacienteId}/tratamientos`,
      { headers: H }
    );
    const fila = (await trat.json()).data.find((d: any) => String(d.ident) === String(actoId));
    expect(fila.facturado).toBe(true);
  });

  test('15.11: la radiografía y sus hallazgos siguen accesibles al final del flujo', async ({ request }) => {
    const list = await request.get(`${API}/pacientes/${pacienteId}/radiologia`, { headers: H });
    const img = (await list.json()).find((i: any) => i.id === imagenId);
    expect(img).toBeTruthy();
    expect(img.hallazgos.length).toBeGreaterThan(0);
  });

  test('15.12: auth — un token inválido no accede a los recursos del paciente', async ({ request }) => {
    const resp = await request.get(`${API}/pacientes/${pacienteId}`, {
      headers: { Authorization: 'Bearer token-invalido', 'X-Centro-Id': String(CENTRO_ID) },
    });
    expect([401, 403]).toContain(resp.status());
  });
});
